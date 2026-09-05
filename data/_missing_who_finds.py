"""Puuttuva seina: loytaako sen JOKIN detektori vai ei YKSIKAAN?

Jalanjaljen sisalla puuttuu 38 GT-instanssia. Kysymys ratkaisee mihin
kannattaa panostaa:
  - jos jokin detektori loytaa ne, vaje on VALINNASSA tai sulautuksessa
  - jos ei yksikaan, se on KYVYKKYYSAUKKO eika viritysasia

`_detector_gt_ab.py` on jo ajanut jokaisen scenen jokaisella detektorilla koko
putken lapi, joten mallit ovat levylla eika mitaan tarvitse ajaa uudelleen.

Kaytto: _missing_who_finds.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FACE = {5, 6, 8, 15}
MIN_PTS = 2000
MIN_FRAC = 0.30
DETS = ("contour", "histogram", "normals")


def _mm(a):
    return a * 1000.0 if len(a) and float(np.ptp(a[:, 0])) < 500.0 else a


def _frac(P, walls) -> float:
    hit = np.zeros(len(P), bool)
    for w in walls:
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = P[:, :2] - a
        half = 0.5 * float(w.get("thickness") or 200.0) + 150.0
        t = d @ u
        hit |= (t >= -150.0) & (t <= L + 150.0) & (np.abs(d @ n) <= half)
    return float(hit.mean())


def _walls(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))["walls"]
    except Exception:
        return None


def main() -> None:
    tot = {"tuotanto": 0, "joku": 0, "eiyksikaan": 0, "kaikki": 0}
    per_det = {d: 0 for d in DETS}
    rows = []
    for i in range(5):
        scene = ROOT / f"data/_rohbau/site_07/scene_0700{i}"
        prod = _walls(ROOT / f"data/output/_matrix/rohbau_0700{i}/floor_00/model.json")
        cand = {d: _walls(ROOT / f"data/output/_detab_0700{i}/{d}/floor_00/model.json")
                for d in DETS}
        if prod is None or any(v is None for v in cand.values()):
            print(f"  scene_0700{i}: mallit puuttuvat, ohitetaan")
            continue
        G = _mm(np.load(scene / "coord.npy").astype(np.float64))
        C = np.load(scene / "class.npy")
        I = np.load(scene / "instance.npy")
        ax = np.array([p for w in prod for p in w["axis"]], float)[:, :2]
        from scipy.spatial import ConvexHull, Delaunay
        hull = Delaunay(ax[ConvexHull(ax).vertices])
        for k in np.unique(I):
            m = I == k
            if m.sum() < MIN_PTS or not np.isin(C[m], list(FACE)).any():
                continue
            P = G[m]
            if float((hull.find_simplex(P[:, :2]) >= 0).mean()) < 0.5:
                continue          # jalanjaljen ULKOPUOLELLA — ei taman vaje
            tot["kaikki"] += 1
            if _frac(P, prod) >= MIN_FRAC:
                tot["tuotanto"] += 1
                continue
            found = [d for d in DETS if _frac(P, cand[d]) >= MIN_FRAC]
            for d in found:
                per_det[d] += 1
            if found:
                tot["joku"] += 1
                L = np.linalg.norm(P[:, :2].max(0) - P[:, :2].min(0))
                rows.append((f"0700{i}", int(k), L / 1000.0, ",".join(found)))
            else:
                tot["eiyksikaan"] += 1

    n = tot["kaikki"]
    print(f"\nGT-instansseja mallin jalanjaljen sisalla: {n}")
    print(f"  tuotanto loytaa                {tot['tuotanto']:3d}  {tot['tuotanto']/n:.3f}")
    print(f"  puuttuu, mutta JOKIN loytaa    {tot['joku']:3d}  {tot['joku']/n:.3f}"
          f"   <== valinta/sulautus")
    print(f"  puuttuu, EI YKSIKAAN loyda     {tot['eiyksikaan']:3d}  {tot['eiyksikaan']/n:.3f}"
          f"   <== kyvykkyysaukko")
    print(f"\nkatto jos valinta olisi taydellinen: "
          f"{(tot['tuotanto']+tot['joku'])/n:.3f}")
    print("\nmika detektori loytaa puuttuvat:",
          {d: per_det[d] for d in DETS})
    if rows:
        print(f"\n{'scene':8s} {'inst':>5s} {'pituus':>7s}  loytaja")
        for s, k, L, f in sorted(rows, key=lambda r: -r[2])[:20]:
            print(f"{s:8s} {k:5d} {L:6.1f} m  {f}")


if __name__ == "__main__":
    main()

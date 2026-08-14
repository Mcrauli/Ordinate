"""Mittaa ehdokasmittarit per seinä ja katso erottavatko ne hyllyn seinästä.

Ajo:  .venv/Scripts/python.exe data/_evidence_probe.py

GT (`_retail_s.ply.gt.json`) kertoo mitkä pinnat ovat AITOJA seiniä ja mitkä
HYLLYN etupintoja, joten jokaiselle detektoidulle seinälle saadaan oikea
label. Vasta jos jokin mittari erottaa ne, se kannattaa viedä tuotantoon.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BAND = 80.0        # mm — kaista pinnan ympärillä pintapisteille
CORE = 60.0        # mm — kohinaikkuna mediaanin ympärillä
CELL = 200.0       # mm — pintapeittoruudun koko


def _seg_dist(p, a, b) -> float:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-9:
        return float(np.linalg.norm(p - a))
    t = max(0.0, min(1.0, float((np.asarray(p, float) - a) @ ab) / L2))
    return float(np.linalg.norm(np.asarray(p, float) - (a + t * ab)))


def label_wall(w, gt) -> str:
    """AITO / HYLLY / MUU — kumpaan GT-pintaan tämä seinä osuu."""
    a = np.array(w["axis"][0], float)
    b = np.array(w["axis"][1], float)
    mid = (a + b) / 2.0
    best = ("MUU", 1e9)
    for g in gt["walls"]:
        d = max(_seg_dist(mid, g["axis"][0], g["axis"][1]),
                _seg_dist(a, g["axis"][0], g["axis"][1]) * 0.0)
        if d < best[1]:
            best = ("AITO", d)
    for s in gt["shelf_faces"]:
        d = _seg_dist(mid, s[0], s[1])
        if d < best[1]:
            best = ("HYLLY", d)
    return best[0] if best[1] < 1500.0 else "MUU"


def metrics(w, pts_all) -> dict:
    a = np.array(w["axis"][0], float)
    b = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(b - a))
    if L < 1.0:
        return {}
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    th = float(w["thickness"])
    z0 = float(w.get("z_min", 0.0))
    h = float(w["height"])

    rel = pts_all[:, :2] - a
    t = rel @ u
    perp = rel @ n
    z = pts_all[:, 2]

    near = (t > 0.0) & (t < L) & (np.abs(perp) < th / 2.0 + 1200.0) \
        & (z > z0 + 100.0) & (z < z0 + h - 100.0)
    if near.sum() < 200:
        return {}
    t_n, perp_n, z_n = t[near], perp[near], z[near]

    # dominoiva puoli = kumpi pinta on paremmin keilattu
    face_band = np.abs(np.abs(perp_n) - th / 2.0) < BAND
    if face_band.sum() < 100:
        return {}
    side = perp_n[face_band] > 0
    s_dom = perp_n[face_band][side] if side.sum() >= (~side).sum() else perp_n[face_band][~side]
    med = float(np.median(s_dom))
    sign = 1.0 if med > 0 else -1.0

    # --- A: pintapeitto (montako ruutua pinnasta on keilattu)
    on_face = (np.abs(perp_n - med) < BAND)
    nt = max(1, int(L / CELL))
    nz = max(1, int(h / CELL))
    ti = np.clip((t_n[on_face] / L * nt).astype(int), 0, nt - 1)
    zi = np.clip(((z_n[on_face] - z0) / h * nz).astype(int), 0, nz - 1)
    filled = len(np.unique(ti * nz + zi))
    coverage = filled / float(nt * nz)

    # --- B: pinnan tasomaisuus (hyllyssä tuotteet eri syvyyksillä)
    core = perp_n[on_face] - med
    core = core[np.abs(core) < CORE]
    noise = float(np.sqrt(np.mean(core ** 2))) if len(core) > 50 else float("nan")

    # --- C: mitä pinnan TAKANA on. Aidon seinän takana ei mitään (tai toinen
    #        pinta terävänä piikkinä); hyllyn takana on tavaraa koko syvyydeltä.
    depth = (perp_n - med) * sign          # >0 = pinnasta poispäin katsojasta
    back = depth[(depth > 150.0) & (depth < 1200.0)]
    nbins = 21
    if len(back) > 50:
        hist, _ = np.histogram(back, bins=nbins, range=(150.0, 1200.0))
        back_fill = float((hist > len(back) / (nbins * 8)).mean())
        back_ratio = len(back) / float(on_face.sum())
    else:
        back_fill, back_ratio = 0.0, 0.0

    return {
        "len_m": L / 1000.0,
        "conf": w["confidence"],
        "coverage": round(coverage, 3),
        "noise": round(noise, 1),
        "back_fill": round(back_fill, 3),
        "back_ratio": round(back_ratio, 3),
    }


def main() -> None:
    gt = json.loads(Path("data/_retail_s.ply.gt.json").read_text(encoding="utf-8"))
    model = json.loads(Path("data/output/_col_fix_s/floor_00/model.json").read_text(encoding="utf-8"))
    print(f"GT: {len(gt['walls'])} aitoa seinää, {len(gt['shelf_faces'])} hyllypintaa")
    for s in gt["shelf_faces"]:
        print(f"   hylly {s[0]} -> {s[1]}")

    pcd = o3d.io.read_point_cloud("data/_retail_s.ply")
    pts = np.asarray(pcd.points)
    print(f"pilvi: {len(pts):,} pistettä\n")

    rows = []
    for w in model["walls"]:
        m = metrics(w, pts)
        if not m:
            continue
        rows.append((label_wall(w, gt), w["id"], m))

    rows.sort(key=lambda r: (r[0], -r[2]["len_m"]))
    print(f"{'label':6s} {'id':10s} {'pituus':>7s} {'conf':>5s} "
          f"{'PEITTO':>7s} {'kohina':>7s} {'takana':>7s} {'tak.os':>7s}")
    for lab, wid, m in rows:
        print(f"{lab:6s} {wid:10s} {m['len_m']:6.1f}m {m['conf']:5.2f} "
              f"{m['coverage']:7.3f} {m['noise']:6.1f} {m['back_fill']:7.3f} {m['back_ratio']:7.3f}")

    print()
    for key in ("coverage", "noise", "back_fill", "back_ratio"):
        for lab in ("AITO", "HYLLY", "MUU"):
            vals = [m[key] for l, _, m in rows if l == lab and not math.isnan(m[key])]
            if vals:
                print(f"  {key:10s} {lab:6s} n={len(vals):2d} "
                      f"min={min(vals):7.3f} med={sorted(vals)[len(vals)//2]:7.3f} max={max(vals):7.3f}")
        print()


if __name__ == "__main__":
    main()

"""Mika signaali erottaa AIDON vastapinnan putkesta? AUC GT-labeloiduista piikeista.

`_thick_peak_probe.py` nayttaa yhden scenen silmalla. Tama kerää kaikki
ehdokaspiikit kaikista sceneista, labeloi ne GT:lla (piikin pisteiden
enemmisto­luokka) ja laskee jokaiselle signaalille AUC:n. Vasta se kertoo
erotteleeko signaali — yksittainen taulukko ei kerro.

Signaalit:
  h        piikin korkeus / maksimi        NYKYINEN kriteeri
  n        piikin pistemaara
  terava   MAD +-6 mm ikkunassa            piikin terävyys (EI tasomaisuus)
  aalto    sarakemediaanien MAD +-20 mm    onko pinta TASO pituussuunnassa
  kate     sarakkeet joissa pisteita       kumottu jo kerran, kontrolli
  levea    piikin puoliarvoleveys

Kaytto: _thick_peak_sweep.py            (kaikki viisi Rohbau-sceneä)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ordinate.core import pipeline as PL  # noqa: E402

_FACE_IDS = {5, 6, 8, 15}          # Wall, Drywall, Parapet, Facade Element
_WIDE = 20.0
_NARROW = 6.0
_COL_MM = 500.0
SCENES = [f"data/_rohbau/site_07/scene_0700{i}" for i in range(5)]
MODELS = [f"data/output/_matrix/rohbau_0700{i}/floor_00/model.json" for i in range(5)]


def _mm(a):
    return a * 1000.0 if len(a) and float(np.ptp(a[:, 0])) < 500.0 else a


def _rows(model_json: Path, scene: Path):
    import open3d as o3d
    walls = json.loads(model_json.read_text(encoding="utf-8"))["walls"]
    pts = _mm(np.asarray(o3d.io.read_point_cloud(str(scene / "cloud.ply")).points))
    G = _mm(np.load(scene / "coord.npy").astype(np.float64))
    C = np.load(scene / "class.npy")
    d, i = cKDTree(G).query(pts, distance_upper_bound=30.0)
    lab = np.where(np.isfinite(d), C[np.clip(i, 0, len(C) - 1)], -1)

    out = []
    for w in walls:
        p0 = np.array(w["axis"][0], float)
        p1 = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(p1 - p0))
        if L < 200.0:
            continue
        along = (p1 - p0) / L
        normal = np.array([-along[1], along[0]])
        z0 = float(w.get("z_min") or 0.0)
        h = float(w.get("height") or 0.0)
        ap = (pts[:, :2] - p0) @ along
        dd = pts[:, :2] @ normal - float(np.dot(normal, p0))
        m = ((ap >= -PL._TL_ALONG_MARGIN) & (ap <= L + PL._TL_ALONG_MARGIN)
             & (np.abs(dd) <= PL._TL_SEARCH)
             & (pts[:, 2] >= z0 + 200.0) & (pts[:, 2] <= z0 + h - 200.0))
        if m.sum() < PL._TL_MIN_PTS:
            continue
        edges = np.arange(-PL._TL_SEARCH, PL._TL_SEARCH + PL._TL_BIN, PL._TL_BIN)
        hist, edges = np.histogram(dd[m], bins=edges)
        centers = 0.5 * (edges[:-1] + edges[1:])
        pks, _ = find_peaks(hist, height=hist.max() * PL._TL_PEAK_FRAC,
                            distance=int(20.0 / PL._TL_BIN))
        if len(pks) < 2:
            continue
        dom = int(max(pks, key=lambda p: hist[p]))
        n_band = int(m.sum())
        dom_n = int((m & (np.abs(dd - float(centers[dom])) <= _NARROW)).sum())
        zb = np.floor(pts[:, 2] / 200.0).astype(np.int64)
        z_all = len(np.unique(zb[m]))
        for p in pks:
            p = int(p)
            if p == dom:
                continue
            sep = abs(float(centers[p]) - float(centers[dom]))
            if not (PL._TL_MIN_THICK <= sep <= PL._TL_MAX_THICK):
                continue
            c = float(centers[p])
            wide = m & (np.abs(dd - c) <= _WIDE)
            nar = m & (np.abs(dd - c) <= _NARROW)
            if nar.sum() < 30 or wide.sum() < 60:
                continue
            g = lab[wide]
            g = g[g >= 0]
            if len(g) < 30:
                continue
            k, v = np.unique(g, return_counts=True)
            top = int(k[int(np.argmax(v))])
            col = np.floor(ap[wide] / _COL_MM).astype(np.int64)
            meds = np.array([np.median(dd[wide][col == c0]) for c0 in np.unique(col)])
            aalto = float(np.median(np.abs(meds - np.median(meds)))) if len(meds) > 2 else np.nan
            dn = dd[nar]
            half = hist[p] / 2.0
            lo = p
            while lo > 0 and hist[lo] > half:
                lo -= 1
            hi = p
            while hi < len(hist) - 1 and hist[hi] > half:
                hi += 1
            zk = len(np.unique(zb[wide])) / max(1, z_all)
            out.append(dict(
                scene=scene.name, wall=w["id"], sep=sep,
                h=float(hist[p] / hist.max()), n=int(nar.sum()),
                terava=float(np.median(np.abs(dn - np.median(dn)))),
                aalto=aalto,
                kate=min(1.0, len(np.unique(col)) / max(1, np.ceil(L / _COL_MM))),
                levea=float((hi - lo) * PL._TL_BIN),
                osuus=float(nar.sum()) / max(1, n_band),
                suht_dom=float(nar.sum()) / max(1, dom_n),
                tiheys=float(nar.sum()) / (L / 1000.0),
                zkate=float(zk),
                face=int(top in _FACE_IDS), cls=top))
    return out


def _auc(x, y):
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    if y.sum() == 0 or y.sum() == len(y):
        return np.nan
    r = np.argsort(np.argsort(x)) + 1.0
    n1 = float(y.sum()); n0 = float(len(y) - n1)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main() -> None:
    rows = []
    for m, s in zip(MODELS, SCENES):
        m, s = ROOT / m, ROOT / s
        if not (m.exists() and (s / "coord.npy").exists()):
            print(f"  ohitettu {s.name}")
            continue
        r = _rows(m, s)
        print(f"  {s.name}: {len(r)} ehdokaspiikkia")
        rows += r
    if not rows:
        raise SystemExit("ei ehdokkaita")
    y = np.array([r["face"] for r in rows])
    print(f"\n{len(rows)} ehdokaspiikkia, joista AITOA PINTAA {int(y.sum())} "
          f"({y.mean():.0%})")
    print(f"\n{'signaali':10s} {'AUC':>6s} {'suunta':>8s}   "
          f"{'aito ka.':>9s} {'vaara ka.':>9s}")
    for k in ("h", "n", "osuus", "suht_dom", "tiheys", "zkate",
              "terava", "aalto", "kate", "levea", "sep"):
        x = np.array([r[k] for r in rows], float)
        a = _auc(x, y)
        d = "isompi" if a >= 0.5 else "pienempi"
        aa = a if a >= 0.5 else 1 - a
        f = np.nanmean(x[y == 1]); g = np.nanmean(x[y == 0])
        print(f"{k:10s} {aa:6.3f} {d:>8s}   {f:9.2f} {g:9.2f}")

    import collections as _c
    byw = _c.defaultdict(list)
    for r in rows:
        byw[(r["scene"], r["wall"])].append(r)
    usable = {k: v for k, v in byw.items() if any(r["face"] for r in v) and len(v) > 1}
    print(f"\nSEINAN SISALLA: {len(usable)} seinaa joilla on >1 ehdokas ja "
          f"ainakin yksi aito pinta")
    print(f"{'signaali':16s} {'osuu aitoon':>12s}")
    for k, hi in (("h", True), ("n", True), ("osuus", True), ("tiheys", True),
                  ("zkate", True), ("aalto", True), ("aalto", False),
                  ("terava", False), ("levea", False), ("sep", False)):
        hit = 0
        for v in usable.values():
            cands = [r for r in v if np.isfinite(r[k])]
            if not cands:
                continue
            b = max(cands, key=lambda r: r[k]) if hi else min(cands, key=lambda r: r[k])
            hit += b["face"]
        nimi = k if hi else k + " (pienin)"
        tag = "  <-- NYKYINEN" if (k == "h" and hi) else ""
        print(f"{nimi:16s} {hit/len(usable):12.3f}{tag}")
    sattuma = np.mean([sum(r["face"] for r in v)/len(v) for v in usable.values()])
    print(f"{'sattuma':16s} {sattuma:12.3f}")
    import collections
    print("\nvaarien ehdokkaiden GT-luokat:",
          dict(collections.Counter(r["cls"] for r in rows if not r["face"]).most_common()))


if __name__ == "__main__":
    main()

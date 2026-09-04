"""Onko paksuuden toinen pinta TASO vai putki? Ehdokaspiikit GT-luokan rinnalla.

`_thickness_lock_wall` valitsee seinan toiseksi pinnaksi TOISEKSI VAHVIMMAN
piikin 50-400 mm etaisyydelta. Kriteeri on siis pistemaara. Putkikellarissa
seinan vieressa kulkeva putkilinja antaa ison piikin, ja AGENTS.md kirjaa
seurauksen mitattuna: malli sanoo 66 mm kun pinnat ovat 225 mm paassa,
mediaanivirhe +109 mm ja 30/57 seinaa yli 100 mm alakanttiin.

Kaksi korjausta on jo kumottu mittauksella: "suosi vastakkaisen puolen
piikkia" (Rohbau menettaa) ja jatkuvuus (kellarin ehdokkailla kate 1.00 joka
ikisella). TASOMAISUUTTA ei ole kokeiltu tassa — ja se on `flatness_prune`in
mukaan ainoa erottelija joka on kestanyt kaikki yhdeksan aineistoa.

Tama EI korjaa mitaan. Se tulostaa jokaiselle ehdokaspiikille kolme lukua ja
GT-luokan, jotta nahdaan EROTTELEEKO tasomaisuus ennen kuin sita viedaan
tuotantoon:
  h     piikin korkeus suhteessa maksimiin  (nykyinen kriteeri)
  mad   kohtisuora hajonta piikin sisalla   (onko se taso)
  kate  sarakkeet joissa piikilla on pisteita (kumottu jo kerran, kontrolli)

Kaytto: _thick_peak_probe.py <model.json> <pilvi.ply> [coord.npy class.npy]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from scan2bim.core import pipeline as PL  # noqa: E402

_REG = {0: "None", 1: "Ceiling", 4: "Floor", 5: "Wall", 6: "Drywall", 8: "Parapet",
        9: "Beam", 10: "Column", 15: "Facade", 17: "TGA"}
_FACE = {"Wall", "Drywall", "Parapet", "Facade"}
_PEAK_HALF = 6.0        # mm — piikin oma kaista kun sen tasomaisuus mitataan
_COL_MM = 500.0


def _wall_hist(w, pts):
    """Sama kaista ja histogrammi kuin `_thickness_lock_wall` — samat vakiot."""
    p0 = np.array(w["axis"][0], float)
    p1 = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(p1 - p0))
    if L < 200.0:
        return None
    along = (p1 - p0) / L
    normal = np.array([-along[1], along[0]])
    axis_D = float(np.dot(normal, p0))
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    ap = (pts[:, :2] - p0) @ along
    d = pts[:, :2] @ normal - axis_D
    m = ((ap >= -PL._TL_ALONG_MARGIN) & (ap <= L + PL._TL_ALONG_MARGIN)
         & (np.abs(d) <= PL._TL_SEARCH)
         & (pts[:, 2] >= z0 + 200.0) & (pts[:, 2] <= z0 + h - 200.0))
    if m.sum() < PL._TL_MIN_PTS:
        return None
    edges = np.arange(-PL._TL_SEARCH, PL._TL_SEARCH + PL._TL_BIN, PL._TL_BIN)
    hist, edges = np.histogram(d[m], bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    pks, _ = find_peaks(hist, height=hist.max() * PL._TL_PEAK_FRAC,
                        distance=int(20.0 / PL._TL_BIN))
    return dict(mask=m, d=d, ap=ap, L=L, hist=hist, centers=centers, pks=pks)


def _peak_stats(H, c: float, gt_cls=None, gt_m=None):
    sel = H["mask"] & (np.abs(H["d"] - c) <= _PEAK_HALF)
    n = int(sel.sum())
    if n < 20:
        return None
    dd = H["d"][sel]
    mad = float(np.median(np.abs(dd - np.median(dd))))
    col = np.floor(H["ap"][sel] / _COL_MM).astype(np.int64)
    ncol = max(1, int(np.ceil(H["L"] / _COL_MM)))
    kate = min(1.0, len(np.unique(col)) / ncol)
    lab = "-"
    if gt_cls is not None:
        g = gt_cls[gt_m & (np.abs(H["d"] - c) <= _PEAK_HALF)] if gt_m is not None else None
        if g is not None and len(g):
            k, v = np.unique(g, return_counts=True)
            top = int(k[int(np.argmax(v))])
            lab = f"{_REG.get(top, top)} {v.max()/v.sum():.0%}"
    return dict(n=n, mad=mad, kate=kate, lab=lab)


def main(model_json: str, cloud: str, coord: str | None = None,
         cls: str | None = None) -> None:
    import open3d as o3d
    walls = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    pts = np.asarray(o3d.io.read_point_cloud(cloud).points)
    if len(pts) and float(np.ptp(pts[:, 0])) < 500.0:
        pts = pts * 1000.0
    G = C = None
    if coord:
        from scipy.spatial import cKDTree
        G = np.load(coord).astype(np.float64)
        if len(G) and float(np.ptp(G[:, 0])) < 500.0:
            G = G * 1000.0
        C = np.load(cls)
        tree = cKDTree(G)
        dist, idx = tree.query(pts, distance_upper_bound=30.0)
        C = np.where(np.isfinite(dist), C[np.clip(idx, 0, len(C) - 1)], -1)

    print(f"{'seina':14s} {'pit m':>6s} {'piikki':>8s} {'etais':>7s} "
          f"{'h':>5s} {'mad':>6s} {'kate':>5s}  {'valinta':9s} GT")
    n_shown = 0
    for w in walls:
        H = _wall_hist(w, pts)
        if H is None or len(H["pks"]) < 2:
            continue
        hist, centers, pks = H["hist"], H["centers"], H["pks"]
        dom = int(max(pks, key=lambda p: hist[p]))
        others = [int(p) for p in pks if int(p) != dom
                  and PL._TL_MIN_THICK <= abs(centers[p] - centers[dom]) <= PL._TL_MAX_THICK]
        if not others:
            continue
        cur = max(others, key=lambda p: hist[p])
        stats = {}
        for p in [dom] + others:
            s = _peak_stats(H, float(centers[p]), C, H["mask"])
            if s:
                stats[p] = s
        flat = min((p for p in others if p in stats), key=lambda p: stats[p]["mad"],
                   default=None)
        if flat is None:
            continue
        n_shown += 1
        L = H["L"] / 1000.0
        for p in [dom] + others:
            if p not in stats:
                continue
            s = stats[p]
            tag = ("DOM" if p == dom else
                   ("nyk+tasom" if p == cur == flat else
                    "NYKYINEN" if p == cur else "tasomaisin" if p == flat else ""))
            print(f"{w['id'][:14]:14s} {L:6.1f} {centers[p]:8.1f} "
                  f"{abs(centers[p]-centers[dom]):7.1f} "
                  f"{hist[p]/hist.max():5.2f} {s['mad']:6.1f} {s['kate']:5.2f}  "
                  f"{tag:9s} {s['lab']}")
    print(f"\n{n_shown} seinaa joilla on vahintaan kaksi kelvollista ehdokasta")


if __name__ == "__main__":
    main(*sys.argv[1:])

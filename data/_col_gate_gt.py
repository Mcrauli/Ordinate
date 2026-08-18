"""Mika portti hylkaa GT-pilarin (Rohbau per-piste luokka 10).

`_col_probe.py` tarvitsee `.gt.json`:n; Rohbaussa totuus on per-piste. Tama
ajaa `detect_columns`:n silmukan samoilla vakioilla mutta kirjaa jokaiselle
komponentille hylkayssyyn ja tasmaa komponentit GT-pilarien keskipisteisiin.

Ajo: _col_gate_gt.py <coord.npy> <model.json>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import label as cc
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _soffit_probe import load_pts  # noqa: E402

import scan2bim.core.segmentation.column_detector as CD  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402


def main(coord_npy: str, model_json: str) -> None:
    P = load_pts(coord_npy)
    sc = Path(coord_npy).parent
    C = np.load(sc / "class.npy").ravel()
    I = np.load(sc / "instance.npy").ravel()
    m = StructuralModel.load(model_json)
    zf = min(s.elevation for s in m.slabs if s.slab_type == "floor")
    zc = max(s.elevation for s in m.slabs if s.slab_type == "ceiling")

    g = C == 10
    ids = np.unique(I[g])
    gt = {}
    for i in ids:
        q = P[g][I[g] == i]
        gt[int(i)] = (q[:, 0].mean(), q[:, 1].mean(), len(q))

    zmask = (P[:, 2] > zf + CD._Z_MARGIN) & (P[:, 2] < zc - CD._Z_MARGIN)
    band = P[zmask]
    free = band[CD._dist_to_walls(band[:, :2], m.walls) > CD._WALL_MARGIN]
    x0, y0 = float(free[:, 0].min()), float(free[:, 1].min())
    ix = ((free[:, 0] - x0) / CD._CELL_MM).astype(np.int64)
    iy = ((free[:, 1] - y0) / CD._CELL_MM).astype(np.int64)
    z_lo = zf + CD._Z_MARGIN
    nz = max(int((zc - CD._Z_MARGIN - z_lo) / CD._ZBIN_MM), 1)
    iz = np.clip(((free[:, 2] - z_lo) / CD._ZBIN_MM).astype(np.int64), 0, nz - 1)
    nx, ny = int(ix.max()) + 1, int(iy.max()) + 1
    counts = np.bincount((ix * ny + iy) * nz + iz, minlength=nx * ny * nz).reshape(nx, ny, nz)
    filled = (counts >= 2).astype(np.int32)
    run = np.zeros_like(filled)
    run[:, :, 0] = filled[:, :, 0]
    for k in range(1, nz):
        run[:, :, k] = (run[:, :, k - 1] + 1) * filled[:, :, k]
    best = run.max(axis=2)
    run_end = run.argmax(axis=2)
    run_start = run_end - best + 1
    cand = best * CD._ZBIN_MM >= min(CD._VFILL_MIN * nz * CD._ZBIN_MM, CD._MIN_ABS_HEIGHT)
    lab, ncomp = cc(cand, structure=np.ones((3, 3), dtype=int))

    tree = cKDTree(P[::4, :2])
    ang = np.linspace(0.0, 2 * np.pi, 8, endpoint=False)

    def why(k: int) -> tuple[str, str]:
        cx_i, cy_i = np.nonzero(lab == k)
        ex = (cx_i.max() - cx_i.min() + 1) * CD._CELL_MM
        ey = (cy_i.max() - cy_i.min() + 1) * CD._CELL_MM
        if not (CD._COMP_MIN_MM <= max(ex, ey) <= CD._COMP_MAX_MM):
            return "komponentin ext", f"{ex:.0f}x{ey:.0f}"
        rx0 = max(cx_i.min() - CD._RING_OUT, 0); rx1 = min(cx_i.max() + CD._RING_OUT + 1, nx)
        ry0 = max(cy_i.min() - CD._RING_OUT, 0); ry1 = min(cy_i.max() + CD._RING_OUT + 1, ny)
        ring = cand[rx0:rx1, ry0:ry1].copy()
        ix0 = max(cx_i.min() - CD._RING_IN, 0); ix1 = min(cx_i.max() + CD._RING_IN + 1, nx)
        iy0 = max(cy_i.min() - CD._RING_IN, 0); iy1 = min(cy_i.max() + CD._RING_IN + 1, ny)
        ring[ix0 - rx0:ix1 - rx0, iy0 - ry0:iy1 - ry0] = False
        if int(ring.sum()) >= CD._RING_MAX_CELLS:
            return "rengas", f"{int(ring.sum())} solua"
        in_comp = ((ix >= cx_i.min() - 1) & (ix <= cx_i.max() + 1)
                   & (iy >= cy_i.min() - 1) & (iy <= cy_i.max() + 1))
        cl = free[in_comp]
        if len(cl) < CD._MIN_CLUSTER_PTS:
            return "pisteita alle MIN_CLUSTER", f"{len(cl)}"
        k_lo = int(run_start[cx_i, cy_i].min()); k_hi = int(run_end[cx_i, cy_i].max())
        base_z = z_lo + k_lo * CD._ZBIN_MM
        top_z = z_lo + (k_hi + 1) * CD._ZBIN_MM
        cl = cl[(cl[:, 2] >= base_z - CD._ZBIN_MM) & (cl[:, 2] <= top_z + CD._ZBIN_MM)]
        if len(cl) < CD._MIN_CLUSTER_PTS:
            return "pisteita jaksossa alle MIN", f"{len(cl)}"
        z_extent = float(cl[:, 2].ptp())
        if z_extent < min(CD._MIN_HEIGHT_FRAC * (zc - zf), CD._MIN_ABS_HEIGHT):
            return "z_extent", f"{z_extent:.0f}"
        xy = cl[:, :2]
        wx = float(np.percentile(xy[:, 0], 98) - np.percentile(xy[:, 0], 2))
        wy = float(np.percentile(xy[:, 1], 98) - np.percentile(xy[:, 1], 2))
        if not (CD._MIN_FOOTPRINT <= max(wx, wy) <= CD._MAX_FOOTPRINT):
            return "footprint", f"{wx:.0f}x{wy:.0f}"
        if max(wx, wy) < CD._MIN_REAL_FOOTPRINT:
            return "ohut footprint", f"{wx:.0f}x{wy:.0f}"
        asp = max(wx, wy) / max(min(wx, wy), 1.0)
        if asp > CD._MAX_ASPECT:
            return "aspekti", f"{asp:.1f} ({wx:.0f}x{wy:.0f})"
        cx = float(xy[:, 0].mean()); cy = float(xy[:, 1].mean())
        if m.walls:
            clear = float(CD._dist_to_walls(np.array([[cx, cy]]), m.walls)[0]) - max(wx, wy) / 2.0
            if clear < CD._MIN_WALL_CLEARANCE:
                return "seinaetaisyys", f"{clear:.0f}"
        probes = np.column_stack([cx + 1000.0 * np.cos(ang), cy + 1000.0 * np.sin(ang)])
        d, _ = tree.query(probes, k=1)
        if int((d < 600.0).sum()) < 5:
            return "surrounded", f"{int((d < 600.0).sum())}/8"
        if not CD._cross_section_stable(cl, base_z - CD._Z_MARGIN, top_z + CD._Z_MARGIN):
            return "poikkileikkaus", ""
        wm = (P[:, 2] > base_z + CD._WAIST_LO) & (P[:, 2] < base_z + CD._WAIST_HI)
        wp = P[wm, :2] if int(wm.sum()) > 200 else None
        wt = cKDTree(wp) if wp is not None else None
        if not CD._waist_isolated(cx, cy, max(wx, wy), wp, wt):
            return "vyotaro", ""
        return "OK", f"{wx:.0f}x{wy:.0f} kork {top_z - base_z:.0f}"

    centers = {}
    for k in range(1, ncomp + 1):
        cx_i, cy_i = np.nonzero(lab == k)
        centers[k] = (x0 + cx_i.mean() * CD._CELL_MM, y0 + cy_i.mean() * CD._CELL_MM)

    print(f"komponentteja {ncomp}, GT-pilareita {len(gt)}")
    print(f"{'inst':>6s} {'n':>7s} {'syy':26s} mitat")
    for i, (gx, gy, n) in sorted(gt.items(), key=lambda t: -t[1][2]):
        near = [k for k, (cx, cy) in centers.items() if abs(cx - gx) < 700 and abs(cy - gy) < 700]
        if not near:
            print(f"{i:6d} {n:7d} {'ei ehdokassoluja':26s}")
            continue
        w, info = min((why(k) for k in near), key=lambda t: t[0] != "OK")
        print(f"{i:6d} {n:7d} {w:26s} {info}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""Jaannoshaun portit TUOTANNON syotepilvella (`_residual_cloud_dump.py`).
Kaytto: _residual_prod_probe.py <dump_dir> <k> <model.json> <wallish.npz>
Tulostaa puuttuvien linjojen solut: onko pintaa, komponentin mitat,
tall-solujen osuus ja tall-alikomponentin mitat."""
import json
import sys

import numpy as np
from scipy.ndimage import label

sys.path.insert(0, "data")
from _missing_line_probe import lines


def main(dump, k, mj, npz):
    import ordinate.core.semantics.residual_walls as RW
    from ordinate.schemas.model import Wall
    z = np.load(f"{dump}/residual_in_{k}.npz")
    pts = z["pts"].astype(float); fz, cz = float(z["fz"]), float(z["cz"])
    walls = [Wall(**w) for w in json.load(open(f"{dump}/residual_walls_{k}.json", encoding="utf-8"))]
    h = cz - fz
    z_lo = fz + min(RW._WAIST_LO_FRAC * h, RW._WAIST_LO_MM); z_hi = fz + RW._WAIST_HI * h
    band = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
    claimed = RW._claimed(band, walls)
    free = band[~claimed]
    o = free[:, :2].min(0)
    ij = np.floor((free[:, :2] - o) / RW._CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    flat = ij[:, 0] * ny + ij[:, 1]
    counts = np.bincount(flat, minlength=nx * ny)
    need = max(RW._SURF_FRAC * float(np.median(counts[counts > 0])), 2.0)
    surf = (counts >= need).reshape(nx, ny)
    tall = RW._tall_cells(free[:, 2], flat, nx * ny, min(RW._MIN_VSPAN_MM, RW._CELL_VSPAN_FRAC * (z_hi - z_lo))).reshape(nx, ny)
    lab, n = label(surf, np.ones((3, 3), int))
    print(f"kaista {z_lo-fz:.0f}..{z_hi-fz:.0f}, vyotarolla {len(band):,}, lunastettu {claimed.mean():.2f}, solukynnys {need:.1f}")
    bxy = band[:, :2]
    for i, r in enumerate(lines(mj, npz, 1500.0)[:16]):
        P = r[6][:, :2]
        pij = np.floor((P - o) / RW._CELL).astype(np.int64)
        ok = (pij[:, 0] >= 0) & (pij[:, 0] < nx) & (pij[:, 1] >= 0) & (pij[:, 1] < ny)
        cells = np.unique(pij[ok, 0] * ny + pij[ok, 1])
        cx, cy = cells // ny, cells % ny
        # lunastettu osuus viivan kohdalla
        from scipy.spatial import cKDTree
        tr = cKDTree(bxy[::5]); d, j = tr.query(P[::5], k=1)
        near = d < 60
        clm = claimed[::5][j[near]].mean() if near.any() else float("nan")
        s_frac = surf[cx, cy].mean(); t_frac = tall[cx, cy].mean()
        ks = lab[cx, cy]; ks = ks[ks > 0]
        dims = "-"
        if len(ks):
            kk = np.bincount(ks).argmax(); ax, ay = np.nonzero(lab == kk)
            xy = np.column_stack([ax, ay]) * RW._CELL; A = xy - xy.mean(0); _, V = np.linalg.eigh(A.T @ A / len(A))
            dims = f"{np.ptp(A @ V[:, 1]) + 100:.0f}x{np.ptp(A @ V[:, 0]) + 100:.0f}"
        print(f"{i:2d} L={r[0]:6.0f} MAD={r[2]:5.1f}: pisteita lahella {near.mean():.2f}, niista lunastettu {clm:.2f}, pintasoluja {s_frac:.2f}, tall {t_frac:.2f}, komp {dims}")


if __name__ == "__main__":
    main(*sys.argv[1:])

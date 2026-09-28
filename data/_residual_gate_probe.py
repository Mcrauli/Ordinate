"""Mika jaannosseinahaun portti hylkaa puuttuvan linjan (GT-vapaa).

Toistaa `find_residual_walls`in komponenttivaiheen ja tulostaa jokaiselle
`_missing_line_probe`-linjalle sen komponentin mitat ja portin joka kaatoi.
Kaytto: _residual_gate_probe.py <model.json> <wallish.npz>
"""
import json
import sys

import numpy as np
from scipy.ndimage import label

sys.path.insert(0, "data")
from _missing_line_probe import lines


def main(mj, npz):
    import ordinate.core.semantics.residual_walls as RW
    from ordinate.schemas.model import StructuralModel
    m = StructuralModel.load(mj)
    z = np.load(npz)
    pts = z["q"].astype(float); fz, cz = float(z["fz"]), float(z["cz"])
    h = cz - fz
    z_lo = fz + min(RW._WAIST_LO_FRAC * h, RW._WAIST_LO_MM); z_hi = fz + RW._WAIST_HI * h
    band = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
    free = band[~RW._claimed(band, m.walls)]
    o = free[:, :2].min(0)
    ij = np.floor((free[:, :2] - o) / RW._CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    flat = ij[:, 0] * ny + ij[:, 1]
    counts = np.bincount(flat, minlength=nx * ny)
    need = max(RW._SURF_FRAC * float(np.median(counts[counts > 0])), 2.0)
    surf = (counts >= need).reshape(nx, ny)
    lab, n = label(surf, np.ones((3, 3), int))
    print(f"kaista {z_lo-fz:.0f}..{z_hi-fz:.0f} mm, vapaita {len(free):,}, solukynnys {need:.1f}, komponentteja {n}")
    for i, r in enumerate(lines(mj, npz, 1500.0)):
        L, P = r[0], r[6]
        pij = np.floor((P[:, :2] - o) / RW._CELL).astype(np.int64)
        ok = (pij[:, 0] >= 0) & (pij[:, 0] < nx) & (pij[:, 1] >= 0) & (pij[:, 1] < ny)
        ks = lab[pij[ok, 0], pij[ok, 1]]
        surf_frac = float((ks > 0).mean()) if len(ks) else 0.0
        if not (ks > 0).any():
            print(f"{i:2d} L={L:6.0f} MAD={r[2]:5.1f}: solut EIVAT ole pintaa ({surf_frac:.2f})"); continue
        k = np.bincount(ks[ks > 0]).argmax()
        cx, cy = np.nonzero(lab == k)
        xy = np.column_stack([cx, cy]).astype(float) * RW._CELL
        A = xy - xy.mean(0); _, V = np.linalg.eigh(A.T @ A / len(A))
        length = float(np.ptp(A @ V[:, 1])) + RW._CELL; width = float(np.ptp(A @ V[:, 0])) + RW._CELL
        q = free[(lab.ravel()[flat] == k)]
        vs = float(np.ptp(q[:, 2]))
        why = []
        if len(cx) < RW._MIN_CELLS: why.append("solut")
        if length < RW._MIN_LEN: why.append("lyhyt")
        if width > RW._MAX_WIDTH: why.append(f"LEVEA {width:.0f}")
        if length / width < RW._MIN_ASPECT: why.append(f"aspekti {length/width:.1f}")
        if vs < min(RW._MIN_VSPAN_MM, RW._MIN_VSPAN_FRAC * (z_hi - z_lo)): why.append(f"pysty {vs:.0f}")
        print(f"{i:2d} L={L:6.0f} MAD={r[2]:5.1f}: komp {len(cx)} solua, {length:.0f}x{width:.0f}, pinta {surf_frac:.2f} -> {', '.join(why) or 'LAPI (pari/lahiseina/ketju)'}")


if __name__ == "__main__":
    main(*sys.argv[1:])

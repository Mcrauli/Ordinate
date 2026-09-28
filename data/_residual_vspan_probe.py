"""Erottaako SOLUN pystyulottuvuus seinan sotkusta jaannoskaistalla?

Kaytto: _residual_vspan_probe.py <model.json> <wallish.npz>
Kohdesolut = puuttuvien tasomaisten linjojen solut; muut = kaikki muut
vapaat solut. Tulostaa pystyulottuvuuden osuuden kaistasta molemmille ja
mita komponentit ovat kun maski rajataan ehdolla vspan >= f.
"""
import sys

import numpy as np
from scipy.ndimage import label

sys.path.insert(0, "data")
from _missing_line_probe import lines


def main(mj, npz):
    import ordinate.core.semantics.residual_walls as RW
    from ordinate.schemas.model import StructuralModel
    m = StructuralModel.load(mj)
    z = np.load(npz); pts = z["q"].astype(float); fz, cz = float(z["fz"]), float(z["cz"])
    h = cz - fz
    z_lo = fz + min(RW._WAIST_LO_FRAC * h, RW._WAIST_LO_MM); z_hi = fz + RW._WAIST_HI * h
    band = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
    free = band[~RW._claimed(band, m.walls)]
    o = free[:, :2].min(0)
    ij = np.floor((free[:, :2] - o) / RW._CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    flat = ij[:, 0] * ny + ij[:, 1]
    order = np.argsort(flat, kind="stable")
    fs = flat[order]; zs = free[order, 2]
    u, st, cnt = np.unique(fs, return_index=True, return_counts=True)
    lo = np.array([np.percentile(zs[a:a + c], 5) for a, c in zip(st, cnt)])
    hi = np.array([np.percentile(zs[a:a + c], 95) for a, c in zip(st, cnt)])
    vfrac = np.zeros(nx * ny); vfrac[u] = (hi - lo) / (z_hi - z_lo)
    occ = np.zeros(nx * ny, bool); occ[u] = True
    tgt = np.zeros(nx * ny, bool)
    rows = lines(mj, npz, 1500.0)
    for r in rows:
        if r[2] > 20: continue
        pij = np.floor((r[6][:, :2] - o) / RW._CELL).astype(np.int64)
        ok = (pij[:, 0] >= 0) & (pij[:, 0] < nx) & (pij[:, 1] >= 0) & (pij[:, 1] < ny)
        tgt[pij[ok, 0] * ny + pij[ok, 1]] = True
    tgt &= occ
    oth = occ & ~tgt
    print(f"kohdesoluja {tgt.sum()}, muita {oth.sum()}")
    for q in (10, 25, 50, 75, 90):
        print(f"  p{q:2d} pystyosuus  kohde {np.percentile(vfrac[tgt], q):.2f}  muut {np.percentile(vfrac[oth], q):.2f}")
    for f in (0.5, 0.6, 0.7, 0.8):
        msk = (occ & (vfrac >= f)).reshape(nx, ny)
        lab, n = label(msk, np.ones((3, 3), int))
        keep_t = (tgt & (vfrac >= f)).sum() / tgt.sum(); keep_o = (oth & (vfrac >= f)).sum() / oth.sum()
        sizes = np.bincount(lab.ravel())[1:]
        tl = lab.ravel()[tgt & (vfrac >= f)]
        big = np.bincount(tl[tl > 0]) if (tl > 0).any() else np.array([0])
        comp = []
        for k in np.unique(tl[tl > 0]):
            cx, cy = np.nonzero(lab == k)
            xy = np.column_stack([cx, cy]).astype(float) * RW._CELL
            A = xy - xy.mean(0); _, V = np.linalg.eigh(A.T @ A / max(len(A), 1))
            comp.append((float(np.ptp(A @ V[:, 1])) + 100, float(np.ptp(A @ V[:, 0])) + 100))
        wide = sum(1 for Lc, w in comp if w > RW._MAX_WIDTH)
        print(f"f>={f}: kohdesoluista jaa {keep_t:.2f}, muista {keep_o:.2f}; kohdekomponentteja {len(comp)}, niista liian leveita {wide}; suurin {max(comp) if comp else None}")


if __name__ == "__main__":
    main(*sys.argv[1:])

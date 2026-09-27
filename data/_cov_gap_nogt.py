"""Mika jaa mallintamatta ILMAN GT:ta: seinamaiset pisteet joita mikaan
mallin seina ei lunasta, piirrettyna mallin paalle.

Kaytto: _cov_gap_nogt.py <model.json> <wallish.npz> <out.png> [band_mm]
wallish.npz: q (N,3) pisteet, m (N,) seinamaisyysmaski (kuten _cache_*_wallish).
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def explained(xy, walls, band):
    hit = np.zeros(len(xy), bool)
    for w in walls:
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        r = xy - a
        t = r @ u; p = r @ n
        hit |= (t > -100) & (t < L + 100) & (np.abs(p) < w["thickness"] / 2 + band)
    return hit


def main(mj, npz, out, band=60.0):
    m = json.load(open(mj, encoding="utf-8"))
    z = np.load(npz)
    q = z["q"][z["m"]].astype(float)
    xy = q[:, :2]
    ex = explained(xy, m["walls"], float(band))
    print(f"seinamaisia {len(q):,}  lunastettu {ex.mean():.3f}  seinia {len(m['walls'])}")
    fig, ax = plt.subplots(figsize=(22, 16), dpi=90)
    s = slice(None, None, max(1, len(q) // 1500000))
    ax.scatter(xy[s][ex[s], 0], xy[s][ex[s], 1], s=0.05, c="#999999")
    ax.scatter(xy[s][~ex[s], 0], xy[s][~ex[s], 1], s=0.08, c="#e0301e")
    for w in m["walls"]:
        a, b = w["axis"]
        ax.plot([a[0], b[0]], [a[1], b[1]], c="#1f4fd1", lw=0.9)
    ax.set_aspect("equal")
    ax.set_title("harmaa = seinamainen piste mallin seinan kaistassa · punainen = ei lunastettu · sininen = mallin seina")
    fig.savefig(out, bbox_inches="tight")


if __name__ == "__main__":
    main(*sys.argv[1:])

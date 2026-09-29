"""GT-seinapisteet (vihrea = mallissa, punainen = puuttuu) + mallin seinat.

Kaytto: _gt_overlay.py <model.json> <scene_dir> <out.png> [vanha model.json]
Sininen = mallin seina, oranssi = normals-lisays, harmaa katkoviiva = vanha malli.
"""
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

STRUCT = (5, 6, 8, 15)


def claimed(xy, walls, band=80.0):
    hit = np.zeros(len(xy), bool)
    for w in walls:
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][-1], float)
        L = np.linalg.norm(b - a)
        if L < 800:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a; s, t = d @ u, d @ n
        hit |= (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2) < band)
    return hit


def main(mj, scene, out, old=None):
    scene = Path(scene)
    m = json.load(open(mj, encoding="utf-8"))
    P = np.load(scene / "coord.npy").astype(float)
    if np.ptp(P[:, 0]) < 500:
        P *= 1000
    C = np.load(scene / "class.npy").ravel()
    zf = min(s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor")
    zc = max(s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling")
    sel = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, c = P[sel, :2], C[sel]
    st = np.isin(c, STRUCT)
    rng = np.random.default_rng(0)
    other = xy[~st][rng.choice((~st).sum(), min((~st).sum(), 150000), replace=False)]
    wxy = xy[st]
    wxy = wxy[rng.choice(len(wxy), min(len(wxy), 250000), replace=False)]
    h = claimed(wxy, m["walls"])
    fig, ax = plt.subplots(figsize=(14, 14))
    ax.scatter(other[:, 0], other[:, 1], s=0.1, c="0.85")
    ax.scatter(wxy[h, 0], wxy[h, 1], s=0.3, c="tab:green")
    ax.scatter(wxy[~h, 0], wxy[~h, 1], s=0.5, c="tab:red")
    if old:
        for w in json.load(open(old, encoding="utf-8"))["walls"]:
            a, b = np.array(w["axis"][0]), np.array(w["axis"][-1])
            ax.plot([a[0], b[0]], [a[1], b[1]], "--", color="0.3", lw=0.8)
    for w in m["walls"]:
        a, b = np.array(w["axis"][0]), np.array(w["axis"][-1])
        new = w["id"].startswith("wall_n_")
        ax.plot([a[0], b[0]], [a[1], b[1]], color="darkorange" if new else "tab:blue", lw=2)
    ax.set_aspect("equal")
    ax.set_title(f"{scene.name}: vihrea=GT-seina mallissa, punainen=puuttuu, oranssi=normals-lisays")
    fig.savefig(out, dpi=80, bbox_inches="tight")


if __name__ == "__main__":
    main(*sys.argv[1:])

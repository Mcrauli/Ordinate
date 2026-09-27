"""Zoomaa alueisiin: koko pilvi harmaana, seinamaiset lunastamattomat punaisina,
mallin seinat sinisina. Kaytto: _cov_zoom_nogt.py <model.json> <wallish.npz> <out.png> x0,y0,x1,y1 [...]"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, "data")
from _cov_gap_nogt import explained


def main(mj, npz, out, *boxes):
    m = json.load(open(mj, encoding="utf-8"))
    z = np.load(npz)
    q = z["q"].astype(float); wm = z["m"]
    fz, cz = float(z["fz"]), float(z["cz"])
    boxes = [tuple(float(v) for v in b.split(",")) for b in boxes]
    fig, axs = plt.subplots(1, len(boxes), figsize=(9 * len(boxes), 9), dpi=90)
    axs = np.atleast_1d(axs)
    for ax, (x0, y0, x1, y1) in zip(axs, boxes):
        s = (q[:, 0] > x0) & (q[:, 0] < x1) & (q[:, 1] > y0) & (q[:, 1] < y1)
        mid = s & (q[:, 2] > fz + 0.3 * (cz - fz)) & (q[:, 2] < fz + 0.7 * (cz - fz))
        ax.scatter(q[mid, 0], q[mid, 1], s=0.3, c="#bbbbbb")
        ws = s & wm
        ex = explained(q[ws, :2], m["walls"], 60.0)
        ax.scatter(q[ws][~ex, 0], q[ws][~ex, 1], s=0.6, c="#e0301e")
        for w in m["walls"]:
            a, b = w["axis"]
            ax.plot([a[0], b[0]], [a[1], b[1]], c="#1f4fd1", lw=1.5)
        ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal")
        ax.set_title(f"{x0:.0f},{y0:.0f} – vyotaro 30–70 % harmaana")
    fig.savefig(out, bbox_inches="tight")


if __name__ == "__main__":
    main(*sys.argv[1:])

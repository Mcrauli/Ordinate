"""Zoomaa yhteen seinään: pilven vyötäröviipale + mallin seinän pinnat.

Kaytto: _zoom_wall.py <model.json> <pilvi.ply> <wall_id_alku> <out.png>
"""
import json
import sys

import matplotlib
import numpy as np
import open3d as o3d

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

mj, ply, wid, out = sys.argv[1:5]
m = json.load(open(mj, encoding="utf-8"))
P = np.asarray(o3d.io.read_point_cloud(ply).points)
if np.ptp(P[:, 0]) < 500:
    P = P * 1000
fz = min(s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor")
cz = max(s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling")
w = next(x for x in m["walls"] if x["id"].startswith(wid))
a, b = np.array(w["axis"][0], float), np.array(w["axis"][-1], float)
L = np.linalg.norm(b - a); u = (b - a) / L; n = np.array([-u[1], u[0]])
d = P[:, :2] - a; t, p = d @ u, d @ n
z = P[:, 2] - fz
sel = (t > -500) & (t < L + 500) & (np.abs(p) < 1500)
fig, ax = plt.subplots(1, 2, figsize=(16, 6))
k = sel & (z > 0.3 * (cz - fz)) & (z < 0.7 * (cz - fz))
ax[0].scatter(t[k], p[k], s=0.3, c="0.4")
for side in (-1, 1):
    ax[0].axhline(side * w["thickness"] / 2, color="red", lw=1)
ax[0].set_title(f"{w['id']} ylhaalta (seinan suunta x, sivuttain y), L={L:.0f} t={w['thickness']}")
k2 = sel & (np.abs(p) < w["thickness"] / 2 + 80)
ax[1].scatter(t[k2], z[k2], s=0.3, c="0.4")
ax[1].set_title("seinan kaistan pisteet sivulta (z lattiasta)")
fig.savefig(out, dpi=80, bbox_inches="tight")
print(w["id"], "kaistassa", int(k2.sum()), "pistetta")

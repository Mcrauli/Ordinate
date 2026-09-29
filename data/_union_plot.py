import json, sys
import numpy as np, open3d as o3d
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
name, ply, out = sys.argv[1], sys.argv[2], sys.argv[3]
P = np.asarray(o3d.io.read_point_cloud(ply).points)
if np.ptp(P[:, 0]) < 500: P = P * 1000
m = json.load(open(f"data/output/_union/{name}/floor_00/model.json", encoding="utf-8"))
fz = min(s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor")
S = P[(P[:, 2] > fz + 1000) & (P[:, 2] < fz + 1300)]
S = S[np.random.default_rng(0).choice(len(S), min(len(S), 300000), replace=False)]
fig, ax = plt.subplots(figsize=(16, 12))
ax.scatter(S[:, 0], S[:, 1], s=0.2, c="0.6")
for w in m["walls"]:
    a, b = np.array(w["axis"][0]), np.array(w["axis"][-1])
    new = w["id"].startswith("wall_n_")
    ax.plot([a[0], b[0]], [a[1], b[1]], color="red" if new else "blue", lw=2.5 if new else 1.5)
    if new: ax.text(*(a + b) / 2, w["id"][7:], fontsize=7, color="red")
ax.set_aspect("equal"); fig.savefig(out, dpi=90, bbox_inches="tight")

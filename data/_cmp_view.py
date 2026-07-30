"""Yleinen ennen/jalkeen-overlay: pilvi + seinat + huoneet + lattiakontuuri.
Kaytto: _cmp_view.py <ply> <model_a.json> <model_b.json> <out.png>"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
from shapely.geometry import Polygon

from scan2bim.core.geometry.loader import load_point_cloud

ply, pa, pb, outpng = sys.argv[1:5]
c = load_point_cloud(Path(ply)).voxel_down_sample(30.0)
P = np.asarray(c.points); z = P[:, 2]
zf, zc = np.percentile(z, 2), np.percentile(z, 98)
mid = P[(z > zf + 0.35 * (zc - zf)) & (z < zf + 0.6 * (zc - zf))]

fig, axs = plt.subplots(1, 2, figsize=(24, 13))
for ax, path in zip(axs, (pa, pb)):
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    ax.scatter(mid[:, 0], mid[:, 1], s=0.6, c="0.3", linewidths=0)
    tot = 0.0
    for s in m["spaces"]:
        b = np.array([[float(x), float(y)] for x, y in s["boundary"]])
        if len(b) >= 3:
            tot += Polygon(b).area
            ax.add_patch(MP(b, closed=True, facecolor="#9f9", alpha=0.3, edgecolor="#2a2", lw=1))
    for w in m["walls"]:
        a = np.array(w["axis"][0], float); bb = np.array(w["axis"][1], float)
        d = bb - a; L = np.linalg.norm(d)
        if L < 1:
            continue
        u = d / L; n = np.array([-u[1], u[0]]); h = w["thickness"] / 2
        fp = w["source"]["method"] == "floorplan"
        ax.add_patch(MP([a+n*h, bb+n*h, bb-n*h, a-n*h], closed=True,
                        facecolor="#f22" if fp else "#26f", alpha=0.45,
                        edgecolor="#a00" if fp else "#04c", lw=1.3))
        ax.text(*(a+bb)/2, w["id"].replace("wall_", "").replace("ext_", "E"),
                fontsize=8, color="#600" if fp else "#004", ha="center")
    ax.set_aspect("equal")
    ax.set_title(f"{Path(path).parent.parent.name}: {len(m['walls'])} seinaa "
                 f"({sum(1 for w in m['walls'] if w['source']['method']=='floorplan')} perim) "
                 f"{len(m['spaces'])} huonetta {tot/1e6:.1f} m2")
plt.savefig(outpng, dpi=95, bbox_inches="tight")
print("saved", outpng)

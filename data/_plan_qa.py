"""Pohjapiirros-diagnoosi: seinät paksuussuorakaiteina pilven päällä.
Punainen = mittaamaton paksuus (seed/1-puolinen), sininen = mitattu.
Näyttää raot, tyngät, päällekkäisyydet.
"""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import open3d as o3d

ROOT = Path(r"C:\Users\lauri\scan2bim")
m = json.loads((ROOT / "data/output/_contour_ifc/floor_00/model.json").read_text())
xy = np.load(ROOT / "data/_qa_band_xy.npy")
sub = xy[::40]

fig, ax = plt.subplots(figsize=(13, 13))
ax.scatter(sub[:, 0], sub[:, 1], s=0.2, c="0.75", linewidths=0)

SEED = {200.0, 60.0, 65.0, 70.0}  # tyypilliset seed-arvot (epäluotettava)
for w in m["walls"]:
    a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
    d = b - a; L = np.linalg.norm(d)
    if L < 1: continue
    u = d / L; n = np.array([-u[1], u[0]]); h = w["thickness"] / 2
    corners = [a + n*h, b + n*h, b - n*h, a - n*h]
    seed = round(w["thickness"], 1) in SEED or w["thickness"] >= 250
    col = "#d33" if seed else "#36c"
    ax.add_patch(Polygon(corners, closed=True, facecolor=col, alpha=0.45, edgecolor=col, lw=1))
    mid = 0.5*(a+b)
    ax.text(mid[0], mid[1], f"{w['id'].replace('wall_','')}\n{w['thickness']:.0f}", fontsize=6, ha="center", va="center")

ax.set_aspect("equal"); ax.set_title("POHJA: punainen=mittaamaton/epäilyttävä paksuus, sininen=mitattu")
out = ROOT / "data/_plan_qa.png"
plt.savefig(out, dpi=110, bbox_inches="tight")
print("saved", out)

"""Pohjapiirros: malliseinat + GT-seinat + hyllyt + tilat samaan kuvaan.

Aja:  .venv\\Scripts\\python data/_retail_view.py data/output/_scale_s data/_retail_s.ply.gt.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

out_dir = Path(sys.argv[1])
gt = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
png = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("data/_retail_plan.png")

model = json.loads(sorted(out_dir.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))

fig, ax = plt.subplots(figsize=(18, 12))

for g in gt["walls"]:
    a, b = np.array(g["axis"], float)
    ax.plot([a[0], b[0]], [a[1], b[1]], color="0.75", lw=6, solid_capstyle="butt", zorder=1)
for a, b in gt.get("shelf_faces", []):
    a, b = np.array(a, float), np.array(b, float)
    ax.plot([a[0], b[0]], [a[1], b[1]], color="orange", lw=4, ls=":", zorder=2)
if gt.get("columns"):
    c = np.array(gt["columns"], float)
    ax.scatter(c[:, 0], c[:, 1], s=14, c="0.6", marker="s", zorder=2)

for s in model.get("spaces", []):
    b = np.array(s["boundary"], float)
    if len(b) >= 3:
        ax.fill(b[:, 0], b[:, 1], color="tab:green", alpha=0.18, zorder=0)

for w in model["walls"]:
    a, b = np.array(w["axis"], float)
    ax.plot([a[0], b[0]], [a[1], b[1]], color="tab:blue", lw=1.8, zorder=3)
    m = (a + b) / 2
    ax.annotate(f"{w['id'][5:]}·{w['thickness']:.0f}", m, fontsize=6,
                color="tab:red", ha="center", zorder=4)

if model.get("columns"):
    c = np.array([x["location"][:2] for x in model["columns"]], float)
    ax.scatter(c[:, 0], c[:, 1], s=26, facecolors="none", edgecolors="tab:purple", zorder=4)

by_id = {w["id"]: np.array(w["axis"], float) for w in model["walls"]}
for o in model.get("openings", []):
    ax_ = by_id.get(o.get("wall_id"))
    if ax_ is None:
        continue
    a, b = ax_
    u = (b - a) / max(np.linalg.norm(b - a), 1e-6)
    p = a + o["position_along"] * u
    ax.scatter(*p, s=45, c="tab:red",
               marker="x" if o["opening_type"] == "window" else "+", zorder=5)

ax.set_aspect("equal")
ax.set_title(f"{out_dir.name}: {len(model['walls'])} seinaa (sin), GT harmaa, hylly oranssi, "
             f"tilat vihrea")
fig.tight_layout()
fig.savefig(png, dpi=110)
print(png)

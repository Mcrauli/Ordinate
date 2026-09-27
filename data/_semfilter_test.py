"""Testaa SemanticFilter: before/after-overlay + säilytys-% (kalustettu huone)."""
import sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import open3d as o3d
from ordinate.core.geometry.loader import load_point_cloud
from ordinate.core.segmentation.semantic_filter import SemanticFilter

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(str(DOWNLOADS / "aligned_low_bedroom/bedroom.ply"))
c = load_point_cloud(SRC)
n0 = len(c.points)
print(f"sisaan: {n0} pistetta")

import time; t = time.time()
from _paths import DATA, DOWNLOADS  # portable dev-tool paths
out = SemanticFilter().filter(c)
n1 = len(out.points)
print(f"ulos:   {n1} pistetta  ({100*n1/n0:.0f}% sailytetty)  {time.time()-t:.1f}s")

# before/after top-down (koko korkeus projisoituna)
pa = np.asarray(c.points); pb = np.asarray(out.points)
fig, ax = plt.subplots(1, 2, figsize=(20, 10))
for axi, p, title in [(ax[0], pa, f"ENNEN ({n0})"), (ax[1], pb, f"JALKEEN ({n1})")]:
    s = p[::max(1, len(p)//400000)]
    axi.scatter(s[:, 0], s[:, 1], s=0.2, c="0.4", linewidths=0)
    axi.set_aspect("equal"); axi.set_title(title)
out_png = Path(str(DATA / "_semfilter.png"))
plt.savefig(out_png, dpi=90, bbox_inches="tight"); print("saved", out_png)

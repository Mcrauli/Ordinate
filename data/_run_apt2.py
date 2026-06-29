"""Aja contour-pipeline TOISELLE asunnolle (apt.ply) + overlay + plan."""
import json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import open3d as o3d
from scan2bim.core.pipeline import Pipeline, PipelineConfig
from scan2bim.core.geometry.loader import load_point_cloud

SRC = Path(r"C:\Users\lauri\Downloads\aligned_low_apartment\apt.ply")
OUT = Path(r"C:\Users\lauri\scan2bim\data\output\_apt2_ifc")

cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=True, export_dxf=False, export_qa=False)
models = Pipeline(cfg).run_floors([SRC], OUT)
m = json.loads((OUT / "floor_00" / "model.json").read_text())
print("walls=%d spaces=%d doors=%d" % (len(m["walls"]), len(m.get("spaces", [])),
      sum(1 for o in m.get("openings", []) if o["opening_type"] == "door")))
print("paksuudet:", sorted(set(round(w["thickness"]) for w in m["walls"])))

# overlay: malli seinät (paksuussuorakaiteina) pilven z-kaistan päällä
c = load_point_cloud(SRC)
p = np.asarray(c.points); z = p[:, 2]
fz, cz = z.min(), z.max()
band = p[(z > fz + 0.4*(cz-fz)) & (z < fz + 0.6*(cz-fz))]
sub = band[::20]
fig, ax = plt.subplots(figsize=(12, 12))
ax.scatter(sub[:, 0], sub[:, 1], s=0.2, c="0.7", linewidths=0)
for w in m["walls"]:
    a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
    d = b - a; L = np.linalg.norm(d)
    if L < 1: continue
    u = d/L; n = np.array([-u[1], u[0]]); h = w["thickness"]/2
    ax.add_patch(Polygon([a+n*h, b+n*h, b-n*h, a-n*h], closed=True,
                 facecolor="#36c", alpha=0.45, edgecolor="#06c", lw=1))
ax.set_aspect("equal"); ax.set_title("APT2 (toinen asunto): malli vs pilvi  %d seinaa %d huonetta" % (len(m["walls"]), len(m.get("spaces", []))))
out = Path(r"C:\Users\lauri\scan2bim\data\_apt2_overlay.png")
plt.savefig(out, dpi=110, bbox_inches="tight"); print("saved", out)

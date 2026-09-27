"""Aja contour-pipeline 3DSES-testialueelle (oikea TLS + CAD-GT) + overlay."""
import glob, json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import open3d as o3d
from ordinate.core.pipeline import Pipeline, PipelineConfig
from _paths import DATA, OUTPUT  # portable dev-tool paths

D = Path(str(DATA / "_3dses"))
PLY = D / "_3dses_cloud.ply"
OUT = Path(str(OUTPUT / "_3dses_ifc"))

if not PLY.exists():
    parts = []
    for f in sorted(glob.glob(str(D / "*.npy"))):
        a = np.load(f)
        parts.append(a[:, :3])   # XYZ metreissä
        print("ladattu", Path(f).name, a.shape)
    pts = np.vstack(parts)
    pc = o3d.geometry.PointCloud(); pc.points = o3d.utility.Vector3dVector(pts)
    o3d.io.write_point_cloud(str(PLY), pc)
    print("yhdistetty", len(pts), "pistettä ->", PLY)

cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=True, export_dxf=False, export_qa=False)
models = Pipeline(cfg).run_floors([PLY], OUT)
m = json.loads((OUT / "floor_00" / "model.json").read_text())
print("walls=%d spaces=%d doors=%d" % (len(m["walls"]), len(m.get("spaces", [])),
      sum(1 for o in m.get("openings", []) if o["opening_type"] == "door")))
print("paksuudet:", sorted(set(round(w["thickness"]) for w in m["walls"])))

# overlay
c = o3d.io.read_point_cloud(str(PLY)); p = np.asarray(c.points); z = p[:, 2]
fz, cz = np.percentile(z, 2), np.percentile(z, 98)
band = p[(z > fz + 0.4*(cz-fz)) & (z < fz + 0.6*(cz-fz))]
sub = band[::max(1, len(band)//400000)]
fig, ax = plt.subplots(figsize=(12, 12))
ax.scatter(sub[:, 0], sub[:, 1], s=0.2, c="0.7", linewidths=0)
for w in m["walls"]:
    a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
    d = b - a; L = np.linalg.norm(d)
    if L < 1: continue
    u = d/L; n = np.array([-u[1], u[0]]); h = w["thickness"]/2
    ax.add_patch(Polygon([a+n*h, b+n*h, b-n*h, a-n*h], closed=True,
                 facecolor="#36c", alpha=0.45, edgecolor="#06c", lw=1))
ax.set_aspect("equal"); ax.set_title("3DSES (oikea TLS): %d seinaa %d huonetta" % (len(m["walls"]), len(m.get("spaces", []))))
out = D / "_3dses_overlay.png"
plt.savefig(out, dpi=110, bbox_inches="tight"); print("saved", out)

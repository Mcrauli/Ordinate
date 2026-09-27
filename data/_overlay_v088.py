import json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import open3d as o3d
from scan2bim.core.geometry.loader import load_point_cloud

m = json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json").read_text())
apt = Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")
# lataa yksi keilaus kevyeksi taustaksi (harvennettu)
c = load_point_cloud(sorted(apt.glob("scan_*.ply"))[0])
c = c.voxel_down_sample(25.0)
p = np.asarray(c.points); z = p[:, 2]
fz, cz = np.percentile(z, 2), np.percentile(z, 98)
band = p[(z > fz+0.4*(cz-fz)) & (z < fz+0.6*(cz-fz))]

fig, ax = plt.subplots(figsize=(13, 13))
ax.scatter(band[:,0], band[:,1], s=0.4, c="0.72", linewidths=0)
for w in m["walls"]:
    a=np.array(w["axis"][0],float); b=np.array(w["axis"][1],float); d=b-a; L=np.linalg.norm(d)
    if L<1: continue
    u=d/L; n=np.array([-u[1],u[0]]); h=w["thickness"]/2
    ax.add_patch(Polygon([a+n*h,b+n*h,b-n*h,a-n*h],closed=True,facecolor="#26f",alpha=0.4,edgecolor="#04c",lw=1.3))
for op in m.get("openings",[]):
    pass
ax.set_aspect("equal")
ax.set_title(f"v0.8.8 PointNet: {len(m['walls'])} seinaa {len(m.get('spaces',[]))} huonetta "
             f"{sum(1 for o in m.get('openings',[]) if o['opening_type']=='door')} ovea")
out = Path(r"C:\Users\lauri\scan2bim\data\_overlay_v088.png")
plt.savefig(out, dpi=105, bbox_inches="tight"); print("saved", out)
print("paksuudet:", sorted(set(round(w["thickness"]) for w in m["walls"])))

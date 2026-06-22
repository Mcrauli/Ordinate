"""Nopea tarkkuusiterointi: lataa cachattu pilvi, aja _detect, piirrä. ~sekunteja."""
from pathlib import Path
import open3d as o3d, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scan2bim.core.pipeline import Pipeline, PipelineConfig

cloud = o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_cache_apt.ply")
cfg = PipelineConfig(detector="contour", auto_voxel=False, voxel_size=12.0,
                     export_ifc=False, export_dxf=False, export_qa=False)
pipe = Pipeline(cfg)
m = pipe._detect(cloud, Path("apt"))
print(f"walls={len(m.walls)} spaces={len(m.spaces)} "
      f"doors={sum(1 for o in m.openings if o.opening_type=='door')}")

fig, ax = plt.subplots(figsize=(10,10))
import matplotlib.cm as cm
for i,sp in enumerate(m.spaces):
    b=sp.boundary+[sp.boundary[0]]
    ax.fill([p[0] for p in b],[p[1] for p in b],alpha=.3)
    c=np.mean(sp.boundary,axis=0); ax.annotate(f"R{i}",c,ha="center",weight="bold")
for w in m.walls:
    (x0,y0),(x1,y1)=w.axis
    ax.plot([x0,x1],[y0,y1],"-",lw=max(w.thickness/25,1.5),color="#333",solid_capstyle="round")
ax.set_aspect("equal"); ax.grid(alpha=.2)
ax.set_title(f"{len(m.walls)} walls, {len(m.spaces)} rooms")
out=r"C:\Users\lauri\scan2bim\data\_iter.png"; plt.savefig(out,dpi=110,bbox_inches="tight")
print("saved",out)

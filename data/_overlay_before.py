"""Vision: TUOTANNON malli (_contour_ifc model.json) vs täysiresa pistepilvi."""
import json, math, numpy as np, open3d as o3d
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from _paths import DATA, OUTPUT  # portable dev-tool paths
m=json.loads(Path(str(OUTPUT / "_contour_ifc/floor_00/model.json")).read_text())
band=np.asarray(o3d.io.read_point_cloud(str(DATA / "_qa_band.ply")).points)
xy=band[:,:2]
rs=np.random.RandomState(0); xy=xy[rs.choice(len(xy),min(600000,len(xy)),replace=False)]
GRID=35.0
x0,y0=xy[:,0].min(),xy[:,1].min()
nx=int((xy[:,0].max()-x0)/GRID)+1; ny=int((xy[:,1].max()-y0)/GRID)+1
H,_,_=np.histogram2d(xy[:,0],xy[:,1],bins=[nx,ny],range=[[x0,x0+nx*GRID],[y0,y0+ny*GRID]])
fig,ax=plt.subplots(figsize=(13,13))
ax.imshow(np.log1p(H.T),origin="lower",extent=[x0,x0+nx*GRID,y0,y0+ny*GRID],cmap="Greys",aspect="equal")
for w in m["walls"]:
    (ax0,ay0),(ax1,ay1)=w["axis"]
    ax.plot([ax0,ax1],[ay0,ay1],"-",lw=2,color="#0aa",alpha=.9)
for o in m["openings"]:
    w=next((w for w in m["walls"] if w["id"]==o["wall_id"]),None)
    if not w: continue
    (ax0,ay0),(ax1,ay1)=w["axis"];L=math.hypot(ax1-ax0,ay1-ay0) or 1;t=o["position_along"]/L
    px,py=ax0+(ax1-ax0)*t,ay0+(ay1-ay0)*t
    ax.plot(px,py,"s",ms=12,color="lime" if o["opening_type"]=="door" else "orange",mec="k")
ax.set_title(f'TUOTANTO 0.4.3 vs pistepilvi: {len(m["walls"])} seinaa, {sum(1 for o in m["openings"] if o["opening_type"]=="door")} ovea, {len(m["spaces"])} huonetta')
ax.set_aspect("equal")
out=str(DATA / "_overlay_prod.png");plt.savefig(out,dpi=100,bbox_inches="tight");print("saved",out)

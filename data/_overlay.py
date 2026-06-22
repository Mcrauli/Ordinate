"""Overlay: pistepilven tiheys ovikorkeudelta + detektoidut seinät/ovet päälle."""
from pathlib import Path
import open3d as o3d, numpy as np, math
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scan2bim.core.pipeline import Pipeline, PipelineConfig

cloud = o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_cache_apt.ply")
pts = np.asarray(cloud.points)
z = pts[:,2]; zmin,zmax = z.min(), z.max(); span=zmax-zmin
# ovikaista: ~0.3-1.0 lattiasta (oviaukot näkyvät rakoina; ikkuna jättää sillin)
lo, hi = zmin+0.15*span, zmin+0.95*span
band = pts[(z>=lo)&(z<=hi)]
GRID=40.0
x0,y0=band[:,0].min(),band[:,1].min()
nx=int((band[:,0].max()-x0)/GRID)+1; ny=int((band[:,1].max()-y0)/GRID)+1
H,_,_=np.histogram2d(band[:,0],band[:,1],bins=[nx,ny],
    range=[[x0,x0+nx*GRID],[y0,y0+ny*GRID]])
H=H.T

cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,
    export_ifc=False,export_dxf=False,export_qa=False)
m=Pipeline(cfg)._detect(cloud,Path("apt"))

fig,ax=plt.subplots(figsize=(13,13))
ax.imshow(np.log1p(H),origin="lower",extent=[x0,x0+nx*GRID,y0,y0+ny*GRID],
    cmap="Greys",alpha=.9,aspect="equal")
for w in m.walls:
    (ax0,ay0),(ax1,ay1)=w.axis
    ax.plot([ax0,ax1],[ay0,ay1],"-",lw=2.2,color="#39d0d8",alpha=.9)
for o in m.openings:
    w=next((w for w in m.walls if w.id==o.wall_id),None)
    if not w: continue
    (ax0,ay0),(ax1,ay1)=w.axis; L=math.hypot(ax1-ax0,ay1-ay0) or 1; t=o.position_along/L
    px,py=ax0+(ax1-ax0)*t,ay0+(ay1-ay0)*t
    col="lime" if o.opening_type=="door" else "orange"
    ax.plot(px,py,"s",ms=14,color=col,mec="k")
    ax.annotate(o.opening_type,(px,py),color=col,fontsize=11,weight="bold")
ax.set_title(f"Pistepilvi (harmaa) vs detektoidut seinät (cyan) + aukot. "
    f"{len(m.walls)} walls, {sum(1 for o in m.openings if o.opening_type=='door')} doors")
ax.set_aspect("equal")
out=r"C:\Users\lauri\scan2bim\data\_overlay.png"; plt.savefig(out,dpi=100,bbox_inches="tight")
print("walls",len(m.walls),"doors",sum(1 for o in m.openings if o.opening_type=='door'),
      "windows",sum(1 for o in m.openings if o.opening_type=='window'))
print("saved",out)

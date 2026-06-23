"""1.5mm tarkkuus-QA + vision-heatmap. Detektoi 12mm cachella, mittaa täysiresa-bandia vasten."""
from pathlib import Path
import open3d as o3d, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scan2bim.core.pipeline import Pipeline, PipelineConfig

TOL=1.5
det=o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_cache_apt.ply")
cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,
    export_ifc=False,export_dxf=False,export_qa=False)
m=Pipeline(cfg)._detect(det,Path("apt"))

band=np.asarray(o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_qa_band.ply").points)
xy=band[:,:2]
dmin=np.full(len(xy),9e9)
for w in m.walls:
    a=np.array(w.axis[0],float);b=np.array(w.axis[1],float);ab=b-a;L2=ab@ab
    if L2<1e-9: continue
    t=np.clip(((xy-a)@ab)/L2,0,1); proj=a+t[:,None]*ab
    d=np.abs(np.linalg.norm(xy-proj,axis=1)-w.thickness/2)  # etäisyys seinäPINTAAN
    dmin=np.minimum(dmin,d)

assoc=dmin[dmin<50.0]   # vain seinän lähipisteet (ei kalusteet/keskilattia)
print(f"=== 1.5mm QA (seinäpinta, {len(assoc):,} assoc-pistettä) ===")
for tol in (1.5,2.5,5.0,10.0):
    print(f"  <{tol:4.1f}mm: {100*np.mean(assoc<tol):.1f}%")
print(f"  mean={assoc.mean():.2f} median={np.median(assoc):.2f} p95={np.percentile(assoc,95):.2f} mm")

# heatmap
fig,ax=plt.subplots(figsize=(12,12))
sub=dmin<50.0
sc=ax.scatter(xy[sub,0],xy[sub,1],c=np.minimum(dmin[sub],10),s=1,cmap="RdYlGn_r",vmin=0,vmax=10)
for w in m.walls:
    (x0,y0),(x1,y1)=w.axis; ax.plot([x0,x1],[y0,y1],"-",color="black",lw=1,alpha=.5)
plt.colorbar(sc,label="poikkeama seinäpinnasta (mm, clamp 10)")
ax.set_aspect("equal")
ax.set_title(f"1.5mm QA: {100*np.mean(assoc<TOL):.1f}% <1.5mm, mediaani {np.median(assoc):.2f}mm")
out=r"C:\Users\lauri\scan2bim\data\_qa_heatmap.png"; plt.savefig(out,dpi=100,bbox_inches="tight")
print("saved",out)

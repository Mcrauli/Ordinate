from pathlib import Path
import open3d as o3d, numpy as np
from ordinate.core.pipeline import Pipeline, PipelineConfig
from _paths import DATA  # portable dev-tool paths
cloud=o3d.io.read_point_cloud(str(DATA / "_cache_apt.ply"))
cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,
    export_ifc=False,export_dxf=False,export_qa=False)
m=Pipeline(cfg)._detect(cloud,Path("apt"))
W=m.walls
# 1) auki olevat nurkat: seinänpää >150mm kaikista muista seinistä
def pt_seg(p,a,b):
    ab=b-a;L2=ab@ab
    if L2<1e-9: return np.linalg.norm(p-a)
    t=max(0,min(1,(p-a)@ab/L2));return np.linalg.norm(p-(a+t*ab))
open_ends=0;tot_ends=0
for w in W:
    for ep in (np.array(w.axis[0],float),np.array(w.axis[1],float)):
        tot_ends+=1
        dmin=min((pt_seg(ep,np.array(o.axis[0],float),np.array(o.axis[1],float))
                  for o in W if o.id!=w.id),default=9e9)
        if dmin>150: open_ends+=1
print(f"Nurkat: {open_ends}/{tot_ends} seinänpäätä auki (>150mm muista)")
# 2) paksuudet
th=[w.thickness for w in W]
print(f"Paksuudet: min={min(th):.0f} max={max(th):.0f} mediaani={np.median(th):.0f} mm, uniikkeja={len(set(round(t/10) for t in th))}")
# 3) geometrinen tarkkuus: % pisteistä <25mm jostain seinästä (seinäkaista)
pts=np.asarray(cloud.points);z=pts[:,2]
fz=min((s.elevation for s in m.slabs if s.slab_type=="floor"),default=z.min())
cz=max((s.elevation for s in m.slabs if s.slab_type=="ceiling"),default=z.max())
band=pts[(z>fz+300)&(z<cz-300)][:,:2]
if len(band)>200000:
    band=band[np.random.RandomState(0).choice(len(band),200000,replace=False)]
dmin=np.full(len(band),9e9)
for w in W:
    a=np.array(w.axis[0],float);b=np.array(w.axis[1],float);ab=b-a;L2=ab@ab
    if L2<1e-9: continue
    t=np.clip(((band-a)@ab)/L2,0,1)
    proj=a+t[:,None]*ab
    d=np.linalg.norm(band-proj,axis=1)-w.thickness/2
    dmin=np.minimum(dmin,np.abs(d))
for tol in (25,50,100):
    print(f"  {100*np.mean(dmin<tol):.1f}% seinäkaistan pisteistä <{tol}mm jostain seinästä")

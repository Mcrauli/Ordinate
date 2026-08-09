from pathlib import Path
import open3d as o3d, numpy as np
from scan2bim.core.pipeline import Pipeline, PipelineConfig
from scan2bim.core.segmentation import opening_detector as od
from _paths import DATA  # portable dev-tool paths

cloud = o3d.io.read_point_cloud(str(DATA / "_cache_apt.ply"))
cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,
    export_ifc=False,export_dxf=False,export_qa=False)
# aja _detect mutta nappaa seinät juuri ennen openings
m=Pipeline(cfg)._detect(cloud,Path("apt"))
pts=np.asarray(cloud.points)
floor_z=min((s.elevation for s in m.slabs if s.slab_type=="floor"),default=0.0)

print(f"{len(m.walls)} seinää. Per seinä: pituus, pinta-pisteet, baseline, gap-sarakkeet")
for w in m.walls:
    p0=np.array(w.axis[0]);p1=np.array(w.axis[1]);d=p1-p0;L=np.hypot(*d)
    if L<1: continue
    along=d/L;normal=np.array([-along[1],along[0]]);plane_D=normal@p0
    sd=pts[:,:2]@normal-plane_D; dist=np.abs(sd)
    pa=(pts[:,:2]-p0)@along
    zlo=w.z_min-100;zhi=w.z_min+w.height+100
    half=w.thickness/2
    pos=int((np.abs(sd-half)<od._FACE_TOL).sum()); neg=int((np.abs(sd+half)<od._FACE_TOL).sum())
    nf=np.abs(sd-half)<od._FACE_TOL if pos>=neg else np.abs(sd+half)<od._FACE_TOL
    nc=dist<od._FACE_TOL
    mask=(nf|nc)&(pa>=-100)&(pa<=L+100)&(pts[:,2]>=zlo)&(pts[:,2]<=zhi)
    ms=int(mask.sum())
    flag=""
    if ms<50: flag="SKIP(mask<50)"
    print(f"  {w.id} L={L:5.0f} t={w.thickness:3.0f} pinta={ms:5d} {flag}")

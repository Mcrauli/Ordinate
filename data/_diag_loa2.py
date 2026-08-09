"""LOA-bias, akselista riippumaton. Etsii skannatun pinnan LEVEÄSTÄ kaistasta ja
mittaa mallin LÄHIMMÄN pinnan systemaattisen poikkeaman siitä."""
from pathlib import Path
import open3d as o3d, numpy as np
from scan2bim.core.pipeline import Pipeline, PipelineConfig
from scipy.signal import find_peaks
from _paths import DATA  # portable dev-tool paths
det=o3d.io.read_point_cloud(str(DATA / "_cache_apt.ply"))
cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,export_ifc=False,export_dxf=False,export_qa=False)
m=Pipeline(cfg)._detect(det,Path("apt"))
band=np.asarray(o3d.io.read_point_cloud(str(DATA / "_qa_band.ply")).points)[:, :2]

BAND=250.0
biases=[]
for w in m.walls:
    a=np.array(w.axis[0],float);b=np.array(w.axis[1],float);ab=b-a;L=np.linalg.norm(ab)
    if L<1: continue
    u=ab/L;n=np.array([-u[1],u[0]])
    t=(band-a)@u; sd=(band-a)@n
    sel=(t>3)&(t<L-3)&(np.abs(sd)<BAND)
    s=sd[sel]
    if len(s)<300: continue
    h,e=np.histogram(s,bins=int(2*BAND/2),range=(-BAND,BAND)); c=0.5*(e[:-1]+e[1:])
    pk,_=find_peaks(h,height=h.max()*0.3,distance=4)
    if len(pk)==0: continue
    th=w.thickness/2.0
    # mallin kaksi pintaa akselista: +th ja -th. Mitataan jokainen vahva pistepinta
    # lähimpään mallin pintaan -> systemaattinen poikkeama.
    surfs=c[pk]
    counts=h[pk]
    # paino: vahvin pinta dominoi biaksen (yksipuolinen seinä -> 1 pinta)
    dom=surfs[np.argmax(counts)]
    model_face=min(th,-th,key=lambda f:abs(f-dom)) if False else (th if abs(th-dom)<abs(-th-dom) else -th)
    biases.append(abs(model_face-dom))
biases=np.array(biases)
print(f"Seinia: {len(biases)}")
print(f"BIAS (lahin malliPINTA vs skannattu pinta): mediaani={np.median(biases):.1f}mm  keski={biases.mean():.1f}mm  <1.5mm={100*np.mean(biases<1.5):.0f}%  <5mm={100*np.mean(biases<5):.0f}%")

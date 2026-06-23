"""Erottele centerline-virhe vs paksuusvirhe vs keilaimen kohina."""
from pathlib import Path
import open3d as o3d, numpy as np
from scan2bim.core.pipeline import Pipeline, PipelineConfig
det=o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_cache_apt.ply")
cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,export_ifc=False,export_dxf=False,export_qa=False)
m=Pipeline(cfg)._detect(det,Path("apt"))
band=np.asarray(o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_qa_band.ply").points)
xy=band[:,:2]
rs=np.random.RandomState(0); idx=rs.choice(len(xy),min(400000,len(xy)),replace=False); xy=xy[idx]

# per piste: lähin seinä + SIGNED kohtisuora etäisyys sen centerlinestä
best=np.full(len(xy),9e9); signed=np.zeros(len(xy)); whose=np.full(len(xy),-1)
halfs=[]
for wi,w in enumerate(m.walls):
    a=np.array(w.axis[0],float);b=np.array(w.axis[1],float);ab=b-a;L=np.linalg.norm(ab)
    if L<1: continue
    u=ab/L;n=np.array([-u[1],u[0]])
    t=((xy-a)@u)
    inside=(t>=-50)&(t<=L+50)
    sd=(xy-a)@n
    d=np.abs(sd)
    upd=inside&(d<best)
    best[upd]=d[upd]; signed[upd]=sd[upd]; whose[upd]=wi
    halfs.append(w.thickness/2)

# Yhden hyvän seinän tarkka analyysi: eniten assoc-pisteitä
import collections
cnt=collections.Counter(whose[best<60])
wi,_=cnt.most_common(1)[0]
w=m.walls[wi]
sd=signed[(whose==wi)&(best<60)]
print(f"PARAS seinä {w.id}: {len(sd)} pistettä, det_paksuus={w.thickness:.0f} (half={w.thickness/2:.0f})")
# pistemassan pinnat: histogrammi signed-etäisyydestä
h,edges=np.histogram(sd,bins=120,range=(-60,60))
centers=0.5*(edges[:-1]+edges[1:])
from scipy.signal import find_peaks
pk,_=find_peaks(h,height=h.max()*0.2,distance=3)
print("  pintapiikit (mm centerlinestä):", [f"{centers[p]:.1f}" for p in pk])
# kohina: piikin leveys (std lähellä suurinta piikkiä)
if len(pk):
    main=centers[pk[np.argmax(h[pk])]]
    near=sd[np.abs(sd-main)<8]
    print(f"  pääpiikki @ {main:.1f}mm, kohina(std)={near.std():.2f}mm  -> keilaimen raja ~{2*near.std():.1f}mm")

# KOKO malli: jos siirtäisimme jokaisen seinän pinnan pistemassan piikkiin, montako <1.5mm?
# eli "paras mahdollinen" jos paksuus+centerline täydellinen per seinä
assoc=best<60
print(f"\nKOKO malli, nyt: {100*np.mean(best[assoc]<1.5):.1f}% <1.5mm centerline-etäisyys EI mielekäs")

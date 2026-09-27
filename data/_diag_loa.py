"""LOA-oikea mittari: per seinä, mallin pinnan SYSTEMAATTINEN poikkeama pistepinnasta (bias)
vs keilaimen per-piste kohina. + oracle: paras mahd. <1.5mm jos paksuus täydellinen."""
from pathlib import Path
import open3d as o3d, numpy as np
from ordinate.core.pipeline import Pipeline, PipelineConfig
from scipy.signal import find_peaks
from _paths import DATA  # portable dev-tool paths
det=o3d.io.read_point_cloud(str(DATA / "_cache_apt.ply"))
cfg=PipelineConfig(detector="contour",auto_voxel=False,voxel_size=12.0,export_ifc=False,export_dxf=False,export_qa=False)
m=Pipeline(cfg)._detect(det,Path("apt"))
band=np.asarray(o3d.io.read_point_cloud(str(DATA / "_qa_band.ply")).points)[:, :2]

biases=[]; noises=[]; oracle_hits=0; oracle_tot=0; cur_hits=0
for w in m.walls:
    a=np.array(w.axis[0],float);b=np.array(w.axis[1],float);ab=b-a;L=np.linalg.norm(ab)
    if L<1: continue
    u=ab/L;n=np.array([-u[1],u[0]])
    t=(band-a)@u; sd=(band-a)@n
    sel=(t>3)&(t<L-3)&(np.abs(sd)<40)   # tiukka: tämän seinän lähipisteet
    s=sd[sel]
    if len(s)<300: continue
    # dominantti pistepinta (piikki)
    h,e=np.histogram(s,bins=160,range=(-40,40)); c=0.5*(e[:-1]+e[1:])
    pk,_=find_peaks(h,height=h.max()*0.3,distance=4)
    if len(pk)==0: continue
    surf=c[pk[np.argmax(h[pk])]]           # pistepinnan sijainti centerlinestä
    near=s[np.abs(s-surf)<6]
    noise=near.std()                        # keilaimen kohina tällä pinnalla
    model_surf=np.sign(surf)*w.thickness/2  # mallin pinta samalla puolella
    bias=abs(model_surf-surf)               # SYSTEMAATTINEN poikkeama
    biases.append(bias); noises.append(noise)
    # oracle: jos malli osuu pintaan täydellisesti, montako <1.5mm (kohinan rajoittama)
    oracle_hits+=int((np.abs(near-surf)<1.5).sum()); oracle_tot+=len(near)
    cur_hits+=int((np.abs(near-model_surf)<1.5).sum())

biases=np.array(biases);noises=np.array(noises)
print(f"Seiniä analysoitu: {len(biases)}")
print(f"MALLIN SIJAINTIVIRHE (bias, LOA): mediaani={np.median(biases):.1f}mm  keski={biases.mean():.1f}mm  <1.5mm-seiniä={100*np.mean(biases<1.5):.0f}%")
print(f"KEILAIMEN KOHINA (per piste std): mediaani={np.median(noises):.2f}mm")
print(f"ORACLE per-piste <1.5mm (täydellinen malli, kohinan katto): {100*oracle_hits/max(oracle_tot,1):.1f}%")
print(f"NYKYINEN per-piste <1.5mm (pinta): {100*cur_hits/max(oracle_tot,1):.1f}%")

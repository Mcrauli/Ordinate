"""Own-surface bias: per seinä, lähin OMA pinta (±120mm band) vs skannattu pinta."""
import json, numpy as np, open3d as o3d
from pathlib import Path
from scipy.signal import find_peaks
m=json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_contour_ifc\floor_00\model.json").read_text())
band=np.asarray(o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_qa_band.ply").points)[:,:2]
biases=[]
for w in m['walls']:
    a=np.array(w['axis'][0],float);b=np.array(w['axis'][1],float);ab=b-a;L=np.linalg.norm(ab)
    if L<1: continue
    u=ab/L;n=np.array([-u[1],u[0]]);t=(band-a)@u;sd=(band-a)@n
    half=w['thickness']/2
    # etsi pistepinta lähin mallin lähimmästä pinnasta (±120mm siitä)
    for face in (half,-half):
        sel=(t>3)&(t<L-3)&(np.abs(sd-face)<120); s=sd[sel]
        if len(s)<200: continue
        h,e=np.histogram(s,bins=120,range=(face-120,face+120));c=0.5*(e[:-1]+e[1:])
        pk,_=find_peaks(h,height=h.max()*0.3,distance=4)
        if len(pk)==0: continue
        surf=c[pk[np.argmax(h[pk])]]
        biases.append(abs(face-surf)); break
b=np.array(biases)
print(f'OWN-SURFACE bias ({len(b)} seinaa): mediaani={np.median(b):.1f}mm keski={b.mean():.1f}mm '
      f'<1.5mm={100*np.mean(b<1.5):.0f}% <3mm={100*np.mean(b<3):.0f}% <5mm={100*np.mean(b<5):.0f}%')
print('outlierit >10mm:', sorted([round(x) for x in b if x>10], reverse=True))

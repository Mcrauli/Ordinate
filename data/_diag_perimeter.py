import json
from pathlib import Path
import numpy as np
from scan2bim.core.geometry.loader import load_point_cloud

m=json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json").read_text())
apt=Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")
walls=m["walls"]; z0=min(w["z_min"] for w in walls); h=max(w["height"] for w in walls)
lo,hi=z0+0.25*h,z0+0.75*h   # laaja seinäkaista
pts=[]
for f in sorted(apt.glob("scan_*.ply")):
    p=np.asarray(load_point_cloud(f).points); pts.append(p[(p[:,2]>=lo)&(p[:,2]<=hi)][::4])
band=np.vstack(pts); xy=band[:,:2]
print("kaista",len(xy),"pistettä")

BIN=200.0; FACE=120.0  # pistetuki: pisteitä ±FACE mm seinäakselista, per BIN pitkin
def support(w):
    a=np.array(w["axis"][0],float); b=np.array(w["axis"][1],float); d=b-a; L=np.linalg.norm(d)
    if L<1: return 0.0,0
    u=d/L; n=np.array([-u[1],u[0]]); rel=xy-a
    t=rel@u; perp=rel@n
    th=max(w["thickness"],200.0)
    msk=(t>=0)&(t<=L)&(np.abs(perp)<=th/2+FACE)
    nb=max(int(L/BIN),1)
    if msk.sum()==0: return 0.0,nb
    hh,_=np.histogram(t[msk],bins=nb,range=[0,L])
    return float((hh>=3).mean()), nb   # osuus reunasta jolla on pistetukea

print("\nid            method     thickness  pistetuki%  binit")
for w in sorted(walls,key=lambda w:w["source"]["method"]!="floorplan"):
    frac,nb=support(w)
    flag=" <-- HAAMU?" if (w["source"]["method"]=="floorplan" and frac<0.15) else ""
    print("  %-13s %-10s %6.0f     %4.0f%%      %3d%s"%(w["id"],w["source"]["method"],w["thickness"],100*frac,nb,flag))

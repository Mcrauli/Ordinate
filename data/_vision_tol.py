"""Vision: seinät värikoodattuna PAKSUUS-toleranssin mukaan pistepilven päälle."""
import json, numpy as np, open3d as o3d
from pathlib import Path
from scipy.signal import find_peaks
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
m=json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_contour_ifc\floor_00\model.json").read_text())
band=np.asarray(o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_qa_band.ply").points)
xy=band[:,:2]
fig,ax=plt.subplots(figsize=(13,13))
GRID=40.0;x0,y0=xy[:,0].min(),xy[:,1].min()
nx=int((xy[:,0].max()-x0)/GRID)+1;ny=int((xy[:,1].max()-y0)/GRID)+1
H,_,_=np.histogram2d(xy[:,0],xy[:,1],bins=[nx,ny],range=[[x0,x0+nx*GRID],[y0,y0+ny*GRID]])
ax.imshow(np.log1p(H.T),origin="lower",extent=[x0,x0+nx*GRID,y0,y0+ny*GRID],cmap="Greys",aspect="equal",alpha=.8)
g=y=r=o=0
for w in m['walls']:
    a=np.array(w['axis'][0],float);b=np.array(w['axis'][1],float);ab=b-a;L=np.linalg.norm(ab)
    if L<1: continue
    u=ab/L;n=np.array([-u[1],u[0]]);rel=xy-a;t=rel@u;perp=rel@n
    near=(np.abs(perp)<200)&(t>-400)&(t<L+400)
    col="#888"  # yksipuolinen/ei mitattavissa = harmaa
    if near.sum()>=500:
        s=perp[near];h,e=np.histogram(s,bins=np.arange(-200,201,2));c=0.5*(e[:-1]+e[1:])
        pk,_=find_peaks(h,height=h.max()*0.25,distance=10)
        if len(pk)>=2:
            top=sorted(pk,key=lambda p:h[p],reverse=True)[:2];tt=abs(c[top[0]]-c[top[1]])
            if 50<tt<400:
                err=abs(tt-w['thickness'])
                if err<1.5: col="#1a1";g+=1
                elif err<5: col="#dd0";y+=1
                else: col="#e22";r+=1
        if col=="#888": o+=1
    ax.plot([a[0],b[0]],[a[1],b[1]],"-",lw=3,color=col)
ax.set_title(f"PAKSUUS-toleranssi: vihrea<1.5mm({g})  keltainen<5mm({y})  punainen>5mm({r})  harmaa=1-puolinen({o})")
ax.set_aspect("equal")
out=r"C:\Users\lauri\scan2bim\data\_vision_tol.png";plt.savefig(out,dpi=100,bbox_inches="tight");print("saved",out,f"g={g} y={y} r={r} grey={o}")

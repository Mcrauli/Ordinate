import json,sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import open3d as o3d
from scan2bim.core.geometry.loader import load_point_cloud

m=json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json").read_text())
apt=Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")
walls=m["walls"]; z0=min(w["z_min"] for w in walls); h=max(w["height"] for w in walls)
lo,hi=z0+0.42*h,z0+0.58*h
pts=[]
for f in sorted(apt.glob("scan_*.ply")):
    p=np.asarray(load_point_cloud(f).points); pts.append(p[(p[:,2]>=lo)&(p[:,2]<=hi)][::2])
band=np.vstack(pts)

regions={"topright":(1200,3200,-400,1900),"left":(-6800,-3600,-3400,2000),
         "center":(-1800,900,-3400,-300)}
for name,(x0,x1,y0,y1) in regions.items():
    sel=band[(band[:,0]>=x0)&(band[:,0]<=x1)&(band[:,1]>=y0)&(band[:,1]<=y1)]
    fig,ax=plt.subplots(figsize=(14,14))
    ax.scatter(sel[:,0],sel[:,1],s=0.6,c="0.5",linewidths=0)
    for w in walls:
        a=np.array(w["axis"][0],float); b=np.array(w["axis"][1],float); d=b-a; L=np.linalg.norm(d)
        if L<1: continue
        u=d/L; n=np.array([-u[1],u[0]]); th=w["thickness"]/2
        ax.add_patch(Polygon([a+n*th,b+n*th,b-n*th,a-n*th],closed=True,facecolor="#26f",alpha=0.3,edgecolor="#03a",lw=1.5))
        ax.plot([a[0],b[0]],[a[1],b[1]],"-",color="#03a",lw=0.8)
        mid=0.5*(a+b)
        if x0<mid[0]<x1 and y0<mid[1]<y1:
            ax.text(mid[0],mid[1],f"{w['id'].replace('wall_','')}\n{w['thickness']:.0f}",fontsize=10,ha="center",color="darkred",weight="bold")
        for e in (a,b): ax.plot(e[0],e[1],"o",ms=6,mfc="none",mec="#03a",mew=1.5)
    for op in m.get("openings",[]):
        wl=next((w for w in walls if w["id"]==op["wall_id"]),None)
        if not wl: continue
        a=np.array(wl["axis"][0],float); b=np.array(wl["axis"][1],float); L=np.linalg.norm(b-a)
        if L<1: continue
        u=(b-a)/L; c0=a+u*op["position_along"]; c1=a+u*(op["position_along"]+op["width"])
        col="#e60" if op["opening_type"]=="door" else "#0a0"
        ax.plot([c0[0],c1[0]],[c0[1],c1[1]],"-",color=col,lw=5,solid_capstyle="butt")
    ax.set_xlim(x0,x1); ax.set_ylim(y0,y1); ax.set_aspect("equal"); ax.set_title(f"ZOOM {name}")
    o=Path(fr"C:\Users\lauri\scan2bim\data\_zoom_{name}.png")
    plt.savefig(o,dpi=95,bbox_inches="tight"); print("saved",o); plt.close()

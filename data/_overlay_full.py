import json
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import open3d as o3d
from scan2bim.core.geometry.loader import load_point_cloud

m = json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json").read_text())
apt = Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")

# yhdistä KAIKKI 7 keilausta, keskikaista täydellä-ish resalla
walls = m["walls"]
z0 = min(w["z_min"] for w in walls); h = max(w["height"] for w in walls)
lo, hi = z0 + 0.42*h, z0 + 0.58*h   # kapea keskikaista -> seinät teräviä viivoja
pts = []
for f in sorted(apt.glob("scan_*.ply")):
    c = load_point_cloud(f)
    p = np.asarray(c.points)
    band = p[(p[:,2] >= lo) & (p[:,2] <= hi)]
    pts.append(band[::3])   # kevyt harvennus
    print("ladattu", f.name, len(band), flush=True)
band = np.vstack(pts)
print("keskikaista yht", len(band), flush=True)

fig, ax = plt.subplots(figsize=(20, 20))
sub = band[::max(1, len(band)//1500000)]
ax.scatter(sub[:,0], sub[:,1], s=0.25, c="0.55", linewidths=0)

for w in walls:
    a=np.array(w["axis"][0],float); b=np.array(w["axis"][1],float); d=b-a; L=np.linalg.norm(d)
    if L<1: continue
    u=d/L; n=np.array([-u[1],u[0]]); th=w["thickness"]/2
    ax.add_patch(Polygon([a+n*th,b+n*th,b-n*th,a-n*th],closed=True,facecolor="#26f",alpha=0.32,edgecolor="#03a",lw=1.4))
    ax.plot([a[0],b[0]],[a[1],b[1]],"-",color="#03a",lw=0.7)
    mid=0.5*(a+b)
    ax.text(mid[0],mid[1],f"{w['id'].replace('wall_','')}\n{w['thickness']:.0f}",fontsize=7,ha="center",va="center",color="darkred")
    for e in (a,b):
        ax.plot(e[0],e[1],"o",ms=4,mfc="none",mec="#03a",mew=1)

# aukot: sijainti seinällä
for op in m.get("openings",[]):
    wl = next((w for w in walls if w["id"]==op["wall_id"]), None)
    if not wl: continue
    a=np.array(wl["axis"][0],float); b=np.array(wl["axis"][1],float); L=np.linalg.norm(b-a)
    if L<1: continue
    u=(b-a)/L
    c0=a+u*op["position_along"]; c1=a+u*(op["position_along"]+op["width"])
    col="#e60" if op["opening_type"]=="door" else "#0a0"
    ax.plot([c0[0],c1[0]],[c0[1],c1[1]],"-",color=col,lw=4,solid_capstyle="butt")

ax.set_aspect("equal")
ax.set_title(f"v0.8.8 TARKASTUS: {len(walls)} seinaa, {len(m.get('spaces',[]))} huonetta, "
             f"oranssi=ovi vihrea=ikkuna | keskikaista {len(band)} pistetta")
out = Path(r"C:\Users\lauri\scan2bim\data\_overlay_full.png")
plt.savefig(out, dpi=115, bbox_inches="tight"); print("saved", out)

import json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

p = Path(sys.argv[1])
m = json.loads(p.read_text())
fig, ax = plt.subplots(figsize=(11,11))

# spaces (filled)
for i,sp in enumerate(m.get("spaces",[])):
    b=sp["boundary"]+[sp["boundary"][0]]
    xs=[v[0] for v in b]; ys=[v[1] for v in b]
    ax.fill(xs,ys,alpha=.25); 
    cx,cy=np.mean([v[0] for v in sp["boundary"]]),np.mean([v[1] for v in sp["boundary"]])
    ax.annotate(f'room{i}',(cx,cy),ha="center",fontsize=9,weight="bold")

for s in m["slabs"]:
    if s["slab_type"]=="floor":
        b=s["boundary"]+[s["boundary"][0]]
        ax.plot([v[0] for v in b],[v[1] for v in b],"g--",lw=1,alpha=.5)

for w in m["walls"]:
    (x0,y0),(x1,y1)=w["axis"]
    ax.plot([x0,x1],[y0,y1],"-",lw=max(w["thickness"]/25,1.5),solid_capstyle="round",alpha=.85,color="#333")
    ax.annotate(f'{w["id"].split("_")[1]} t{w["thickness"]:.0f}',((x0+x1)/2,(y0+y1)/2),fontsize=7,ha="center",color="b")

for o in m["openings"]:
    w=next((w for w in m["walls"] if w["id"]==o["wall_id"]),None)
    if not w: continue
    (x0,y0),(x1,y1)=w["axis"]; L=np.hypot(x1-x0,y1-y0); t=o["position_along"]/L if L else 0
    ax.plot(x0+(x1-x0)*t,y0+(y1-y0)*t,"rs",ms=11)

ax.set_aspect("equal"); ax.grid(alpha=.2)
ax.set_title(f'{p.parent.name}: {len(m["walls"])} walls, {len(m.get("spaces",[]))} spaces, {len(m["openings"])} openings')
out=p.with_suffix(".png"); plt.savefig(out,dpi=110,bbox_inches="tight"); print(out)

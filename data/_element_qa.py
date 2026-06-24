"""ELEMENTTIMITTARI v2: paksuus + pituus + päätepisteet raakapisteiden ÄÄRIPÄISTÄ,
luotettavasti (tiheyspohjainen pituus, ei percentile joka nappaa naapurit)."""
import json, numpy as np, open3d as o3d
from pathlib import Path
from scipy.signal import find_peaks

m=json.loads(Path(r"C:\Users\lauri\scan2bim\data\output\_contour_ifc\floor_00\model.json").read_text())
band=np.asarray(o3d.io.read_point_cloud(r"C:\Users\lauri\scan2bim\data\_qa_band.ply").points)
xy=band[:,:2]

def true_extent(ta, L, bin_mm=20.0):
    """Yhtenäinen pistemassa along-suunnassa: laajenna 0 ja L:stä niin kauan kuin
    binit ovat 'täysiä' (>20% mediaanitiheydestä). Palauttaa (lo,hi)."""
    lo_e=min(ta.min(),0); hi_e=max(ta.max(),L)
    bins=np.arange(lo_e-bin_mm, hi_e+bin_mm, bin_mm)
    h,e=np.histogram(ta,bins=bins); c=0.5*(e[:-1]+e[1:])
    occ=h>max(np.median(h[h>0])*0.2,3)
    # seinän keskikohta varmasti täynnä → laajenna siitä
    mid_i=int(np.argmin(np.abs(c-L/2)))
    if not occ[mid_i]: return None
    lo=mid_i
    while lo>0 and occ[lo-1]: lo-=1
    hi=mid_i
    while hi<len(occ)-1 and occ[hi+1]: hi+=1
    return float(c[lo]-bin_mm/2), float(c[hi]+bin_mm/2)

th_err=[]; len_err=[]; end_err=[]
for w in m['walls']:
    a=np.array(w['axis'][0],float); b=np.array(w['axis'][1],float); ab=b-a; L=np.linalg.norm(ab)
    if L<1: continue
    u=ab/L; n=np.array([-u[1],u[0]]); rel=xy-a; t=rel@u; perp=rel@n
    near=(np.abs(perp)<200)&(t>-400)&(t<L+400)
    if near.sum()<500: continue
    s=perp[near]
    h,e=np.histogram(s,bins=np.arange(-200,201,2)); c=0.5*(e[:-1]+e[1:])
    pk,_=find_peaks(h,height=h.max()*0.25,distance=10)
    if len(pk)>=2:
        top=sorted(pk,key=lambda p:h[p],reverse=True)[:2]
        true_th=abs(c[top[0]]-c[top[1]])
        if 50<true_th<400: th_err.append(abs(true_th-w['thickness']))
    surf=near & (np.abs(perp)<60)
    if surf.sum()>300:
        ext=true_extent(t[surf], L)
        if ext:
            lo,hi=ext
            len_err.append(abs((hi-lo)-L)); end_err.append(abs(lo)); end_err.append(abs(hi-L))

def stat(name,arr):
    if not arr: print(f"  {name}: ei dataa"); return
    a=np.array(arr); print(f"  {name}: mediaani={np.median(a):.1f} keski={a.mean():.1f} <1.5mm={100*np.mean(a<1.5):.0f}% <5mm={100*np.mean(a<5):.0f}% <15mm={100*np.mean(a<15):.0f}% (n={len(a)})")
print("ELEMENTTIMITTARI v2:")
stat("PAKSUUS", th_err); stat("PITUUS", len_err); stat("PAATEPISTE", end_err)

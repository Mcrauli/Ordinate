"""Puuttuvien GT-instanssien kartta: luokka, pituus, jalanjalki, loytaako JOKIN ajo sen."""
import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TAGS = sys.argv[1:]
MAIN = TAGS[0]
FACE = (5, 6, 8, 15)
NAMES = {5: "Wall", 6: "Drywall", 8: "Parapet", 15: "Facade"}


def claimed(xy, walls):
    hit = np.zeros(len(xy), bool)
    for w in walls:
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][-1], float)
        L = np.linalg.norm(b - a)
        if L < 800: continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a; s, t = d @ u, d @ n
        hit |= (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2) < 80)
    return hit


stat = collections.Counter(); byclass = collections.Counter(); bylen = collections.Counter()
for mj in sorted((HERE / "output/_wide" / MAIN).glob("scene_*/floor_00/model.json")):
    s = mj.parent.parent.name
    sc = next((HERE / "_rohbau").glob(f"site_*/{s}"))
    P = np.load(sc / "coord.npy").astype(float)
    if np.ptp(P[:, 0]) < 500: P *= 1000
    C = np.load(sc / "class.npy").ravel(); I = np.load(sc / "instance.npy").ravel()
    models = {}
    for t in TAGS:
        p = HERE / "output/_wide" / t / s / "floor_00/model.json"
        if p.exists(): models[t] = json.load(open(p, encoding="utf-8"))
    m = models[MAIN]
    zf = min((x["elevation"] for x in m["slabs"] if x["slab_type"] == "floor"), default=None)
    zc = max((x["elevation"] for x in m["slabs"] if x["slab_type"] == "ceiling"), default=None)
    if zf is None or zc is None: continue
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300) & np.isin(C, FACE)
    xy, c, ins = P[band, :2], C[band], I[band]
    hits = {t: claimed(xy, mm["walls"]) for t, mm in models.items()}
    for i, cnt in zip(*np.unique(ins, return_counts=True)):
        if cnt < 2000: continue
        k = ins == i
        X = xy[k]; cc = collections.Counter(c[k].tolist()).most_common(1)[0][0]
        ctr = X.mean(0); ev, V = np.linalg.eigh(np.cov((X - ctr).T)); L = np.ptp((X - ctr) @ V[:, 1])
        if hits[MAIN][k].mean() >= 0.3: continue
        other = [t for t in TAGS[1:] if t in hits and hits[t][k].mean() >= 0.3]
        cat = "muu ajo loytaa" if other else "ei mikaan"
        stat[cat] += 1; byclass[(cat, NAMES.get(cc, cc))] += 1
        lb = "<1m" if L < 1000 else "1-2m" if L < 2000 else "2-4m" if L < 4000 else ">4m"
        bylen[(cat, lb)] += 1
        if not other and L >= 2000:
            npts_all = int((I == i).sum())
            zz = P[I == i][:, 2]
            print(f"LONG {s} inst {i} {NAMES.get(cc, cc)} L={L/1000:.1f} pisteita {npts_all} z {zz.min()-zf:.0f}..{zz.max()-zf:.0f} (kaista {zc-zf:.0f}) keskipiste {ctr.round()}")
print("puuttuvia:", dict(stat))
for k, v in sorted(byclass.items()): print(" ", k, v)
for k, v in sorted(bylen.items()): print(" ", k, v)

"""Seinan kaistan pystyjakauma: ylaosan tiheys / vyotaron tiheys. Palkkilinja = ylapainoinen.

Kaytto: _topheavy_probe.py <tag>  (kayttaa data/output/_fp_<tag>.csv GT-tuomiot)
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
tag = sys.argv[1]
lab = {(r["scene"], r["id"]): r for r in csv.DictReader(open(HERE / f"output/_fp_{tag}.csv", encoding="utf-8"))}
out = []
for mj in sorted((HERE / "output/_wide" / tag).glob("scene_*/floor_00/model.json")):
    s = mj.parent.parent.name
    sc = next((HERE / "_rohbau").glob(f"site_*/{s}"))
    m = json.load(open(mj, encoding="utf-8"))
    fz = min((x["elevation"] for x in m["slabs"] if x["slab_type"] == "floor"), default=None)
    cz = max((x["elevation"] for x in m["slabs"] if x["slab_type"] == "ceiling"), default=None)
    if fz is None or cz is None:
        continue
    P = np.load(sc / "coord.npy").astype(float)
    if np.ptp(P[:, 0]) < 500:
        P *= 1000
    P = P[np.random.default_rng(0).choice(len(P), min(len(P), 4_000_000), replace=False)]
    H = cz - fz
    for w in m["walls"]:
        r = lab.get((s, w["id"]))
        if r is None:
            continue
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][-1], float)
        L = np.linalg.norm(b - a); u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = P[:, :2] - a; t, p = d @ u, np.abs(d @ n)
        k = (t > 0) & (t < L) & (p < w["thickness"] / 2 + 80)
        z = (P[k, 2] - fz) / H
        waist = ((z > 0.15) & (z < 0.55)).sum() / 0.40
        top = ((z > 0.65) & (z < 0.95)).sum() / 0.30
        ratio = top / max(waist, 1.0)
        out.append((ratio, int(r["true"]), s, w["id"], r["L"], r["gtfrac"]))
out.sort()
fp = [o for o in out if o[1] == 0]; tp = [o for o in out if o[1] == 1]
for thr in (2, 3, 4, 6, 8, 12):
    print(f"ylapaino > {thr:2d}: vale {sum(o[0] > thr for o in fp)}/{len(fp)}, aito {sum(o[0] > thr for o in tp)}/{len(tp)}")
print("suurimmat:")
for o in out[::-1][:25]:
    print(f"  {o[0]:6.1f} {'AITO' if o[1] else 'vale'} {o[2]} {o[3]} L={o[4]} gt={o[5]}")

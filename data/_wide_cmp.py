"""Kahden laajan ajon vertailu scene kerrallaan: GTinst ja GTtark.

Kaytto: _wide_cmp.py <tagA> <tagB>
"""
import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = {r["scene"]: r for r in csv.DictReader(open(HERE / f"output/_wide/{sys.argv[1]}.csv", encoding="utf-8"))}
B = {r["scene"]: r for r in csv.DictReader(open(HERE / f"output/_wide/{sys.argv[2]}.csv", encoding="utf-8"))}
fa = fb = t = 0; pa, pb = [], []; worse, better = [], 0; site = defaultdict(lambda: [0, 0, 0])
for s in sorted(set(A) & set(B)):
    a, b = A[s], B[s]
    if not a["inst_found"] or not b["inst_found"]:
        print("FAIL", s); continue
    ia, ib = int(a["inst_found"]), int(b["inst_found"])
    fa += ia; fb += ib; t += int(a["inst_total"])
    site[s[6:8]][0] += ia; site[s[6:8]][1] += ib; site[s[6:8]][2] += int(a["inst_total"])
    qa, qb = float(a["gt_pre"] or 0), float(b["gt_pre"] or 0)
    if qa > 0: pa.append(qa)
    if qb > 0: pb.append(qb)
    if ib < ia or qb < qa - 0.03:
        worse.append((s, ia, ib, qa, qb))
    elif ib > ia:
        better += 1
print(f"{sys.argv[1]}: {fa}/{t}={fa/t:.3f} tarkkuus ka {statistics.mean(pa):.3f}")
print(f"{sys.argv[2]}: {fb}/{t}={fb/t:.3f} tarkkuus ka {statistics.mean(pb):.3f}")
print(f"parempia {better}, huonompia {len(worse)}")
for k, (x, y, z) in sorted(site.items()):
    print(f"  site_{k}: {x} -> {y} / {z}")
for w in worse:
    print("  huonompi", w)

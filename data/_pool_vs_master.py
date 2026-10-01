"""Poolin tulos vs masterin (final_choice) tulos samoilla sceneilla.

Kaytto: _pool_vs_master.py <pool.log> [master-tag]
"""
import csv
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
tag = sys.argv[2] if len(sys.argv) > 2 else "final_choice"
M = {r["scene"]: r for r in csv.DictReader(open(HERE / f"output/_wide/{tag}.csv", encoding="utf-8"))}
mf = pf = tot = 0; mp, pp = [], []; worse, better = [], []
raw = open(sys.argv[1], "rb").read()
text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8")
for line in text.splitlines():
    if line.startswith("YHT"):
        continue
    p = line.split(); s = p[0]
    m = re.search(r"(\d+)/(\d+)", line)
    if s not in M or not m or not M[s]["inst_found"]:
        continue
    f = int(m.group(1)); pre = float(p[2] or 0); a = M[s]
    mf += int(a["inst_found"]); pf += f; tot += int(a["inst_total"])
    if float(a["gt_pre"] or 0) > 0:
        mp.append(float(a["gt_pre"]))
    if pre > 0:
        pp.append(pre)
    d = (s, a["inst_found"], f, a["gt_pre"], pre)
    if pre < float(a["gt_pre"] or 0) - 0.03 or f < int(a["inst_found"]):
        worse.append(d)
    elif f > int(a["inst_found"]):
        better.append(d)
print(f"master {mf}/{tot}={mf/tot:.3f} tarkkuus ka {statistics.mean(mp):.3f}")
print(f"pooli  {pf}/{tot}={pf/tot:.3f} tarkkuus ka {statistics.mean(pp):.3f}")
print(f"parempia {len(better)}, huonompia {len(worse)}")
for w in worse:
    print("  huonompi", w)


"""Poolin lisaysten hyoty tyomaittain verrattuna masteriin.

Kaytto: _pool_by_site.py <pool.log> [master-tag]
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
tag = sys.argv[2] if len(sys.argv) > 2 else "final_choice"
M = {r["scene"]: r for r in csv.DictReader(open(HERE / f"output/_wide/{tag}.csv", encoding="utf-8"))}
raw = open(sys.argv[1], "rb").read()
text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8")
agg = defaultdict(lambda: [0, 0, 0, 0])
for line in text.splitlines():
    m = re.search(r"(\d+)/(\d+)", line)
    p = line.split()
    if not p or p[0] not in M or not m or not M[p[0]]["inst_found"]:
        continue
    s = p[0]; site = s[6:8]
    agg[site][0] += int(M[s]["inst_found"]); agg[site][1] += int(m.group(1))
    agg[site][2] += int(M[s]["inst_total"]); agg[site][3] += 1
for site, (a, b, t, n) in sorted(agg.items()):
    print(f"site_{site}: {n:2d} scenea  master {a}/{t}  lisayksin {b}/{t}  (+{b - a})")

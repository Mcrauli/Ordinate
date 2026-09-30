"""Valitse scene kerrallaan VALMIS malli GT-vapaalla F1:lla (contour-ketju vs kisa-ketju)."""
import csv
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = {r["scene"]: r for r in csv.DictReader(open(HERE / "output/_wide/base_a15e12f.csv", encoding="utf-8"))}
C = {r["scene"]: r for r in csv.DictReader(open(HERE / "output/_wide/compete_small.csv", encoding="utf-8"))}


def f1(mj, ply):
    out = subprocess.run([sys.executable, str(HERE / "_wall_coverage_nogt.py"), str(mj), str(ply)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    c = float(re.search(r"KATTAVUUS.*?([\d.]+)\s*$", out, re.M).group(1))
    p = float(re.search(r"TARKKUUS.*?([\d.]+)\s*$", out, re.M).group(1))
    return 2 * c * p / (c + p) if c + p else 0.0, c, p


tot = {"base": 0, "kisa": 0, "valinta": 0}; n = 0
for s in sorted(C):
    if A[s]["walls"] == C[s]["walls"] and A[s]["inst_found"] == C[s]["inst_found"] and A[s]["gt_pre"] == C[s]["gt_pre"]:
        continue
    ply = next((HERE / "_rohbau").glob(f"site_*/{s}/cloud.ply"))
    fa = f1(HERE / f"output/_wide/base_a15e12f/{s}/floor_00/model.json", ply)
    fc = f1(HERE / f"output/_wide/compete_small/{s}/floor_00/model.json", ply)
    pick = C[s] if fc[0] > fa[0] else A[s]
    print(f"{s} contourF1 {fa[0]:.3f} kisaF1 {fc[0]:.3f} -> {'KISA' if pick is C[s] else 'cont'}  "
          f"inst {A[s]['inst_found']}/{C[s]['inst_found']} pre {A[s]['gt_pre']}/{C[s]['gt_pre']}", flush=True)

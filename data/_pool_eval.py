"""Ehdokaspooli suodatettuna tarkistimen todennakoisyydella -> GTinst + GTtark.

Kaytto: _pool_eval.py <cand_prob.csv> <kynnys> [perus-tag]
Perus-tag annettuna: malli = perus-tagin malli + poolin seinat jotka ylittavat kynnyksen
ja joita perusmalli ei kata.
"""
import csv
import json
import re
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _union_probe import _ax  # noqa: E402

import numpy as np


def covered(w, walls, near, frac=float(__import__("os").environ.get("POOL_FRAC", "0.5"))):
    a, b = _ax(w)
    L = np.linalg.norm(b - a)
    if L < 1:
        return True
    u = (b - a) / L
    P = a + np.linspace(0, L, max(2, int(L / 100)))[:, None] * u
    hit = np.zeros(len(P), bool)
    for v in walls:
        c, d = _ax(v)
        Lv = np.linalg.norm(d - c)
        if Lv < 1:
            continue
        uv = (d - c) / Lv
        if abs(float(u @ uv)) < np.cos(np.radians(15)):
            continue
        q = P - c
        t = q @ uv
        n = np.abs(q @ np.array([-uv[1], uv[0]]))
        hit |= (t > -near) & (t < Lv + near) & (n < near)
    return hit.mean() >= frac

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
thr = float(sys.argv[2]); base = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
NEAR = float(sys.argv[4]) if len(sys.argv) > 4 else 500.0
by = defaultdict(list)
for r in rows:
    by[r["scene"]].append(r)
F = T = 0; pres = []
for s, rs in sorted(by.items()):
    sc = next((HERE / "_rohbau").glob(f"site_*/{s}"))
    cache = {}
    walls = []
    ref = None
    if base:
        ref = json.load(open(HERE / "output/_wide" / base / s / "floor_00/model.json", encoding="utf-8"))
        walls = list(ref["walls"])
    for r in sorted(rs, key=lambda r: -float(r["prob"])):
        if float(r["prob"]) < thr:
            continue
        if r["src"] not in cache:
            cache[r["src"]] = json.load(open(HERE / "output/_wide" / r["src"] / s / "floor_00/model.json", encoding="utf-8"))
        m = cache[r["src"]]; ref = ref or m
        w = next(w for w in m["walls"] if w["id"] == r["id"])
        if covered(w, walls, NEAR):
            continue
        w = dict(w); w["id"] = r["src"][:3] + "_" + w["id"]
        walls.append(w)
    if ref is None:
        continue
    out = dict(ref); out["walls"] = walls
    tmp = Path(tempfile.gettempdir()) / f"_pool_{s}.json"
    tmp.write_text(json.dumps(out), encoding="utf-8")
    q = subprocess.run([sys.executable, str(HERE / "_rohbau_qa.py"), str(tmp), str(sc / "coord.npy"), str(sc / "class.npy")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    qi = subprocess.run([sys.executable, str(HERE / "_wall_inst_qa.py"), str(tmp), str(sc / "coord.npy"), str(sc / "class.npy")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    pre = re.search(r"TARKKUUS.*?([\d.]+)", q); ins = re.search(r"INSTANSSIKATTAVUUS\s+(\d+)/(\d+)", qi)
    if ins:
        F += int(ins.group(1)); T += int(ins.group(2))
    if pre and float(pre.group(1)) > 0:
        pres.append(float(pre.group(1)))
    print(s, len(walls), pre.group(1) if pre else "", ins.group(0) if ins else "", flush=True)
print(f"YHT kynnys {thr} perus {base} near {NEAR}: inst {F}/{T}={F/T:.3f} tarkkuus ka {statistics.mean(pres):.3f} med {statistics.median(pres):.3f}")


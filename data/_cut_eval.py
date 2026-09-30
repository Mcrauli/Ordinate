"""Poista mallista seinat saannolla ja mittaa GTinst + GTtark kaikissa sceneissa.

Kaytto: _cut_eval.py <tag> <saanto>   esim. "support<0.148"  "continuity<0.22"
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
tag, rule = sys.argv[1], sys.argv[2]
key, thr = re.match(r"(\w+)<([\d.]+)", rule).groups(); thr = float(thr)
F = I = T = 0; pres = []
for mj in sorted((HERE / "output/_wide" / tag).glob("scene_*/floor_00/model.json")):
    s = mj.parent.parent.name
    sc = next((HERE / "_rohbau").glob(f"site_*/{s}"))
    m = json.load(open(mj, encoding="utf-8"))
    before = len(m["walls"])
    m["walls"] = [w for w in m["walls"] if w.get(key) is None or w[key] >= thr]
    tmp = Path(tempfile.gettempdir()) / f"_cut_{s}.json"
    tmp.write_text(json.dumps(m), encoding="utf-8")
    q = subprocess.run([sys.executable, str(HERE / "_rohbau_qa.py"), str(tmp), str(sc / "coord.npy"), str(sc / "class.npy")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    qi = subprocess.run([sys.executable, str(HERE / "_wall_inst_qa.py"), str(tmp), str(sc / "coord.npy"), str(sc / "class.npy")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    pre = re.search(r"TARKKUUS.*?([\d.]+)", q); ins = re.search(r"INSTANSSIKATTAVUUS\s+(\d+)/(\d+)", qi)
    if ins:
        I += int(ins.group(1)); T += int(ins.group(2))
    if pre and float(pre.group(1)) > 0:
        pres.append(float(pre.group(1)))
    print(s, before, "->", len(m["walls"]), pre.group(1) if pre else "", ins.group(0) if ins else "", flush=True)
import statistics
print(f"YHT {rule}: inst {I}/{T}={I/T:.3f}  tarkkuus ka {statistics.mean(pres):.3f} med {statistics.median(pres):.3f}")

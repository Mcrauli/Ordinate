"""Valmis malli A + valmiin mallin B seinat joita A ei kata -> GTinst + GTtark kaikissa sceneissa.

Kaytto: _final_union_eval.py <tagA> <tagB> [near_mm]
"""
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _union_probe import covered  # noqa: E402

HERE = Path(__file__).resolve().parent
ta, tb = sys.argv[1], sys.argv[2]
near = float(sys.argv[3]) if len(sys.argv) > 3 else 300.0
F = T = 0; pres = []
for mj in sorted((HERE / "output/_wide" / ta).glob("scene_*/floor_00/model.json")):
    s = mj.parent.parent.name
    mb = HERE / "output/_wide" / tb / s / "floor_00/model.json"
    sc = next((HERE / "_rohbau").glob(f"site_*/{s}"))
    A = json.load(open(mj, encoding="utf-8"))
    add = []
    if mb.exists():
        B = json.load(open(mb, encoding="utf-8"))
        add = [w for w in B["walls"] if not covered(w, A["walls"], near)]
        for w in add:
            w["id"] = "u_" + w["id"]
    A["walls"] = A["walls"] + add
    tmp = Path(tempfile.gettempdir()) / f"_fu_{s}.json"
    tmp.write_text(json.dumps(A), encoding="utf-8")
    q = subprocess.run([sys.executable, str(HERE / "_rohbau_qa.py"), str(tmp), str(sc / "coord.npy"), str(sc / "class.npy")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    qi = subprocess.run([sys.executable, str(HERE / "_wall_inst_qa.py"), str(tmp), str(sc / "coord.npy"), str(sc / "class.npy")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    pre = re.search(r"TARKKUUS.*?([\d.]+)", q); ins = re.search(r"INSTANSSIKATTAVUUS\s+(\d+)/(\d+)", qi)
    if ins:
        F += int(ins.group(1)); T += int(ins.group(2))
    if pre and float(pre.group(1)) > 0:
        pres.append(float(pre.group(1)))
    print(s, "+", len(add), pre.group(1) if pre else "", ins.group(0) if ins else "", flush=True)
print(f"YHT {ta}+{tb}: inst {F}/{T}={F/T:.3f} tarkkuus ka {statistics.mean(pres):.3f} med {statistics.median(pres):.3f}")

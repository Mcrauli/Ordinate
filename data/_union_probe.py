"""Valitun detektorin malli + toisen detektorin seinat joita valittu ei selita.

Kaytto: _union_probe.py <valittu model.json> <toinen model.json> <scene_dir> [near_mm]
Tulostaa GT-tarkkuuden ja instanssikattavuuden: valittu, toinen, yhdiste.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _ax(w):
    a = np.array(w["axis"][0], float)[:2]
    b = np.array(w["axis"][-1], float)[:2]
    return a, b


def covered(w, walls, near):
    a, b = _ax(w)
    L = np.linalg.norm(b - a)
    if L < 1:
        return True
    u = (b - a) / L
    s = np.linspace(0, L, max(2, int(L / 100)))
    P = a + s[:, None] * u
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
    return hit.mean() >= 0.5


def qa(mj, scene):
    r = subprocess.run([sys.executable, str(HERE / "_rohbau_qa.py"), mj,
                        str(scene / "coord.npy"), str(scene / "class.npy")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    ri = subprocess.run([sys.executable, str(HERE / "_wall_inst_qa.py"), mj,
                         str(scene / "coord.npy"), str(scene / "class.npy")],
                        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    pre = re.search(r"TARKKUUS.*?([\d.]+)", r)
    inst = re.search(r"INSTANSSIKATTAVUUS\s+(\d+/\d+)\s*=\s*([\d.]+)", ri)
    return (pre.group(1) if pre else "?"), (inst.group(1) + " " + inst.group(2) if inst else "?")


def main(a_mj, b_mj, scene, near=600.0):
    near = float(near)
    scene = Path(scene)
    A = json.load(open(a_mj, encoding="utf-8"))
    B = json.load(open(b_mj, encoding="utf-8"))
    add = [w for w in B["walls"] if not covered(w, A["walls"], near)]
    U = dict(A)
    U["walls"] = A["walls"] + add
    tmp = Path(tempfile.gettempdir()) / f"_union_{scene.name}.json"
    tmp.write_text(json.dumps(U), encoding="utf-8")
    for tag, mj, n in (("valittu", a_mj, len(A["walls"])), ("toinen", b_mj, len(B["walls"])),
                       ("yhdiste", str(tmp), len(U["walls"]))):
        pre, inst = qa(mj, scene)
        print(f"{scene.name} {tag:8s} seinia {n:3d}  GTtark {pre}  GTinst {inst}")


if __name__ == "__main__":
    main(*sys.argv[1:])

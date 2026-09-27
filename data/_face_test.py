"""Erotin paksuusparille: seinan RUNGON sisalla ei voi olla KATTOa.
Katto valitaan koska siina ei ole kalusteita (lattia on kalusteen alla piilossa).
Testi vain paksuille seinille: 25 mm ruudukossa ohuen rungosta ei mittaa mitaan.
"""
import json, pathlib
import numpy as np

from scan2bim.core.geometry.loader import load_point_cloud

_MARGIN = 45.0    # mm — pinnan kohinamarginaali rungon sisaan
_BIN = 250.0


def run(name, ply, mj):
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    zc = next(s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling")
    P = np.asarray(load_point_cloud(pathlib.Path(ply)).points)
    cei = P[np.abs(P[:, 2] - zc) < 60.0][:, :2]
    print(f"\n=== {name}")
    print(f"{'wall':13s} {'t':>4s} {'L':>5s}  runko-kaista   kattopeitto rungossa")
    for w in sorted(m["walls"], key=lambda w: -w["thickness"]):
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 800:
            continue
        half = w["thickness"] / 2.0 - _MARGIN
        if half <= 10.0:
            print(f"{w['id']:13s} {w['thickness']:4.0f} {L:5.0f}  (liian ohut testiin)")
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = cei - a; s = d @ u; t = d @ n
        sel = (s > 150) & (s < L - 150) & (np.abs(t) < half)
        nb = max(int(L // _BIN), 1)
        hh, _ = np.histogram(s[sel], bins=nb, range=(0, L))
        cov = float((hh > 3).mean())
        print(f"{w['id']:13s} {w['thickness']:4.0f} {L:5.0f}  +-{half:5.0f} mm     "
              f"{cov:.2f}" + ("   <== PARI EI KELPAA" if cov > 0.60 else ""))


run("apt2", r"C:\Users\lauri\Downloads\aligned_low_apartment\apt.ply",
    "data/output/_val_apt2/floor_00/model.json")
run("raw apartment (v0.8.8 baseline-malli)",
    r"C:\Users\lauri\Downloads\aligned_low_apartment\apt.ply",
    "data/output/_v088_ifc/floor_00/model.json")

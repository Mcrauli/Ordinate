"""Onko tuettomalla seinällä SIIRTYNYT vastine — ja voiko sen napsauttaa paikalleen?

`support == 0` tarkoittaa ettei mallin pinnalla ole pisteitä. Se ei kerro onko
kyse haamusta (ei mitään) vai aidosta seinästä väärässä paikassa. Ero ratkaisee
toimenpiteen: HAAMU poistetaan, SIIRTYNYT napsautetaan mitatulle pinnalle.

Erottelijaksi ehdotetaan: löytyykö ±1000 mm sisältä YHDENSUUNTAINEN pinta joka
on jatkuva seinän pituudelta. Tämä mittaa sen ja tulostaa GT-luokan rinnalle.

Ajo: .venv/Scripts/python.exe data/_snap_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

SEEK = 1000.0      # mm — kuinka kaukaa vastinetta etsitään
BANDW = 60.0       # mm — kaista huipun ympärillä
COL = 500.0        # mm — sarake jatkuvuutta laskettaessa
MINC = 5


def snap_candidate(w, P):
    """(siirtymä mm, vastineen jatkuvuus 0..1) tai None."""
    p0 = np.array(w["axis"][0], float)
    p1 = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(p1 - p0))
    if L < 1.0:
        return None
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    h = float(w["height"])
    z0 = float(w.get("z_min", 0.0))

    rel = P[:, :2] - p0
    t = rel @ u
    perp = rel @ n
    z = P[:, 2]
    sel = ((t > 0) & (t < L) & (np.abs(perp) < SEEK)
           & (z > z0 + 0.30 * h) & (z < z0 + 0.70 * h))   # vyötärö
    if sel.sum() < 200:
        return None
    tp, pp = t[sel], perp[sel]

    hist, edges = np.histogram(pp, bins=80, range=(-SEEK, SEEK))
    peak = 0.5 * (edges[hist.argmax()] + edges[hist.argmax() + 1])
    on = np.abs(pp - peak) < BANDW
    if on.sum() < 100:
        return None
    ncol = max(1, int(L / COL))
    ci = np.clip((tp[on] / L * ncol).astype(int), 0, ncol - 1)
    cont = float((np.bincount(ci, minlength=ncol) >= MINC).mean())
    half = float(w["thickness"]) / 2.0
    return abs(abs(float(peak)) - half), cont


def main() -> None:
    cases = [
        ("data/output/_rohbau_site_07_scene_07000/floor_00/model.json",
         "data/_rohbau/site_07/scene_07000/coord.npy", "ROHBAU",
         {"wall_ext_001": "GT-TYHJA", "wall_ext_007": "GT-TYHJA"}),
        ("data/output/_col_fix_l/floor_00/model.json",
         "data/_retail_l.ply", "KAUPPAKESKUS",
         {"wall_ext_010": "GT-AITO(417mm)"}),
    ]
    for mj, cp, nm, interesting in cases:
        P = (np.load(cp).astype(np.float64) if cp.endswith(".npy")
             else np.asarray(o3d.io.read_point_cloud(cp).points))
        if np.ptp(P[:, 0]) < 500.0:
            P = P * 1000.0
        m = json.loads(Path(mj).read_text(encoding="utf-8"))
        print(f"== {nm}")
        for w in m["walls"]:
            if w["id"] not in interesting:
                continue
            r = snap_candidate(w, P)
            L = float(np.linalg.norm(np.array(w["axis"][1]) - np.array(w["axis"][0])))
            if r is None:
                print(f"  {w['id']:14s} {interesting[w['id']]:15s} L={L/1000:5.1f}m  "
                      f"EI VASTINETTA ±{SEEK:.0f} mm")
            else:
                off, cont = r
                print(f"  {w['id']:14s} {interesting[w['id']]:15s} L={L/1000:5.1f}m  "
                      f"siirtyma={off:6.0f} mm  vastineen jatkuvuus={cont:.2f}")


if __name__ == "__main__":
    main()

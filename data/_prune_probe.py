"""Erottaako VASTINEEN JATKUVUUS haamun siirtyneestä seinästä?

`prune_unsupported_walls` säästää nyt kaiken minkä `support_offset >= 250 mm`.
Se raja perustuu oletukseen että kaukana oleva pinta tarkoittaa SIIRTYNYTTÄ
aitoa seinää. Mutta `_nearest_surface` ottaa histogrammin argmaxin myös
pelkästä kohinasta, joten haamu saa yhtä lailla ison offsetin.

Tämä mittaa jokaiselle seinälle offsetin RINNALLA sen vastineen jatkuvuuden ja
GT-luokan, jotta näkee kumpi suure oikeasti erottelee.

Ajo: .venv/Scripts/python.exe data/_prune_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _snap_probe import snap_candidate  # noqa: E402

_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}
_STRUCT = {"Wall", "Drywall", "Parapet", "Facade Element", "Wall Cutout",
           "Window", "Window Cutout", "Door Rough Opening"}
_BAND = 80.0


def gt_class(w, xy, cls, struct_ids):
    a = np.array(w["axis"][0], float)
    b = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(b - a))
    if L < 1.0:
        return 0.0, 0, "-"
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    d = xy - a
    s, t = d @ u, d @ n
    sel = (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)
    k = int(sel.sum())
    if k == 0:
        return 0.0, 0, "TYHJÄ"
    c = cls[sel]
    vals, cnt = np.unique(c, return_counts=True)
    return float(np.isin(c, list(struct_ids)).mean()), k, _REG.get(int(vals[cnt.argmax()]), "?")


def probe(name, model_json, cloud_path, scene=None):
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    if cloud_path.endswith(".npy"):
        P = np.load(cloud_path).astype(np.float64)
    else:
        P = np.asarray(o3d.io.read_point_cloud(cloud_path).points)
    if np.ptp(P[:, 0]) < 500.0:
        P = P * 1000.0

    xy = cls = struct_ids = None
    if scene is not None:
        C = np.load(Path(scene) / "class.npy").ravel()
        zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
        zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
                 default=zf + 2700)
        band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
        xy, cls = P[band][:, :2], C[band]
        struct_ids = {k for k, v in _REG.items() if v in _STRUCT}

    print(f"\n== {name}  ({len(m['walls'])} seinää)")
    print(f"{'id':16s} {'pit':>6s} {'tuki':>5s} {'jatk':>5s} {'offset':>7s} "
          f"{'vast.jatk':>9s} {'GTpuh':>6s} {'GTluokka':12s}")
    for w in sorted(m["walls"], key=lambda x: x.get("continuity") or 0.0):
        L = float(np.linalg.norm(np.array(w["axis"][1], float) - np.array(w["axis"][0], float)))
        sup = w.get("support")
        con = w.get("continuity")
        off = w.get("support_offset")
        r = snap_candidate(w, P)
        vc = f"{r[1]:9.2f}" if r else "        -"
        gp, gk, gtop = (gt_class(w, xy, cls, struct_ids) if xy is not None else (0.0, 0, "-"))
        print(f"{w['id']:16s} {L/1000:5.1f}m "
              f"{'-' if sup is None else f'{sup:5.2f}'} "
              f"{'-' if con is None else f'{con:5.2f}'} "
              f"{'-' if off is None else f'{off:6.0f}'} {vc} "
              f"{gp:6.2f} {gtop:12s}")


def main() -> None:
    cases = [
        ("ROHBAU site_07/scene_07000",
         "data/output/_rohbau_site_07_scene_07000/floor_00/model.json",
         "data/_rohbau/site_07/scene_07000/coord.npy",
         "data/_rohbau/site_07/scene_07000"),
    ]
    for args in cases:
        if not Path(args[1]).exists():
            print(f"PUUTTUU: {args[1]}")
            continue
        probe(*args)


if __name__ == "__main__":
    main()

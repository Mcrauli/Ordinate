"""Erottavatko evidenssimittarit AIDON seinän VALESEINÄSTÄ Rohbau-GT:llä?

Rohbau3D antaa per-piste luokat, joten jokaiselle detektoidulle seinälle
tiedetään totuus: seinän kaistassa olevien pisteiden GT-luokkajakauma.
"Hyvä" seinä = kaistassa Wall/Drywall/Parapet; "huono" = Beam/TGA/None.

Ajo: .venv/Scripts/python.exe data/_evidence_gt.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _evidence_probe import metrics  # noqa: E402

_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}
_STRUCT = {"Wall", "Drywall", "Parapet", "Facade Element", "Wall Cutout",
           "Window", "Window Cutout", "Door Rough Opening"}
_BAND = 80.0

SCENE = Path("data/_rohbau/site_07/scene_07000")
MODEL = Path("data/output/_rohbau_site_07_scene_07000/floor_00/model.json")


def gt_purity(w, xy, cls, struct_ids) -> tuple[float, int, str]:
    a = np.array(w["axis"][0], float)
    b = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(b - a))
    if L < 1.0:
        return 0.0, 0, "-"
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    d = xy - a
    s = d @ u
    t = d @ n
    sel = (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)
    k = int(sel.sum())
    if k == 0:
        return 0.0, 0, "TYHJÄ"
    c = cls[sel]
    pure = float(np.isin(c, list(struct_ids)).mean())
    vals, cnt = np.unique(c, return_counts=True)
    top = _REG.get(int(vals[cnt.argmax()]), "?")
    return pure, k, top


def main() -> None:
    m = json.loads(MODEL.read_text(encoding="utf-8"))
    P = np.load(SCENE / "coord.npy").astype(np.float64)
    C = np.load(SCENE / "class.npy").ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    print(f"pilvi {len(P):,} pistettä, {len(m['walls'])} seinää")

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, cls = P[band][:, :2], C[band]
    struct_ids = {k for k, v in _REG.items() if v in _STRUCT}

    rows = []
    for w in m["walls"]:
        pure, k, top = gt_purity(w, xy, cls, struct_ids)
        mm = metrics(w, P)
        if not mm:
            mm = {"len_m": 0.0, "conf": w["confidence"], "coverage": float("nan"),
                  "noise": float("nan"), "back_fill": 0.0, "back_ratio": 0.0}
        rows.append((pure, k, top, w["id"], mm))

    rows.sort()
    print(f"\n{'id':12s} {'GTpuhtaus':>9s} {'n':>7s} {'GTluokka':12s} "
          f"{'pituus':>7s} {'conf':>5s} {'PEITTO':>7s} {'kohina':>7s} {'tak.os':>7s}")
    for pure, k, top, wid, mm in rows:
        print(f"{wid:12s} {pure:9.2f} {k:7d} {top:12s} "
              f"{mm['len_m']:6.1f}m {mm['conf']:5.2f} {mm['coverage']:7.3f} "
              f"{mm['noise']:6.1f} {mm['back_ratio']:7.3f}")

    good = [r for r in rows if r[0] >= 0.80 and r[1] > 0]
    badr = [r for r in rows if r[0] < 0.50 or r[1] == 0]
    print(f"\nGT-hyviä {len(good)}, GT-huonoja {len(badr)}")
    for key in ("coverage", "noise", "back_ratio", "conf"):
        for name, grp in (("HYVÄ", good), ("HUONO", badr)):
            vals = [r[4][key] for r in grp if not np.isnan(r[4][key])]
            if vals:
                print(f"  {key:10s} {name:5s} n={len(vals):2d} min={min(vals):7.3f} "
                      f"med={sorted(vals)[len(vals)//2]:7.3f} max={max(vals):7.3f}")
        print()


if __name__ == "__main__":
    main()

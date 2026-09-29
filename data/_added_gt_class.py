"""Jokaisen normals-lisayksen kaistan GT-luokat: onko se seina vai jotain muuta."""
import collections
import json
import sys
from pathlib import Path

import numpy as np

NAMES = {5: "Wall", 6: "Drywall", 8: "Parapet", 15: "Facade", 9: "Beam", 10: "Column",
         17: "TGA", 13: "Window", 14: "Door", 12: "WinCut", 7: "WallCut", 0: "None", 4: "Floor", 1: "Ceil"}
for s in sys.argv[1:]:
    scene = Path(f"data/_rohbau/site_07/scene_{s}")
    m = json.load(open(f"data/output/_union/rohbau_{s}/floor_00/model.json", encoding="utf-8"))
    P = np.load(scene / "coord.npy").astype(float)
    if np.ptp(P[:, 0]) < 500:
        P *= 1000
    C = np.load(scene / "class.npy").ravel()
    I = np.load(scene / "instance.npy").ravel()
    zf = min(x["elevation"] for x in m["slabs"] if x["slab_type"] == "floor")
    zc = max(x["elevation"] for x in m["slabs"] if x["slab_type"] == "ceiling")
    sel = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, c, ins = P[sel, :2], C[sel], I[sel]
    for w in m["walls"]:
        if not w["id"].startswith("wall_n_"):
            continue
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][-1], float)
        L = np.linalg.norm(b - a); u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a; t, p = d @ u, np.abs(d @ n)
        k = (t > 0) & (t < L) & (np.abs(p - w["thickness"] / 2) < 80)
        cnt = collections.Counter(c[k].tolist())
        tot = sum(cnt.values()) or 1
        top = ", ".join(f"{NAMES.get(k_, k_)} {v/tot:.2f}" for k_, v in cnt.most_common(3))
        wi = ins[k & np.isin(c, (5, 6, 8, 15))]
        inst = collections.Counter(wi.tolist()).most_common(1)
        print(f"{s} {w['id']:12s} L={L/1000:4.1f}m  n={tot:6d}  {top}  inst={inst}")

"""Normals-lisayksen suhde pitkiin kohtisuoriin seiniin: ylittaako, kummalla puolella."""
import json
import sys

import numpy as np

for s in sys.argv[1:]:
    m = json.load(open(f"data/output/_union/rohbau_{s}/floor_00/model.json", encoding="utf-8"))
    walls = [(w["id"], np.array(w["axis"][0], float), np.array(w["axis"][-1], float)) for w in m["walls"]]
    cen = np.mean([0.5 * (a + b) for _, a, b in walls if not _.startswith("wall_n_")], axis=0)
    for wid, a, b in walls:
        if not wid.startswith("wall_n_"):
            continue
        L = np.linalg.norm(b - a); u = (b - a) / L
        best = None
        for vid, c, d in walls:
            if vid == wid:
                continue
            Lv = np.linalg.norm(d - c)
            if Lv < 5000:
                continue
            uv = (d - c) / Lv
            if abs(u @ uv) > 0.26:
                continue
            nv = np.array([-uv[1], uv[0]])
            sa, sb = (a - c) @ nv, (b - c) @ nv
            ta, tb = (a - c) @ uv, (b - c) @ uv
            if min(ta, tb) < -300 or max(ta, tb) > Lv + 300:
                continue
            gap = 0.0 if sa * sb < 0 else min(abs(sa), abs(sb))
            if gap > 400:
                continue
            inward = np.sign((cen - c) @ nv)
            out = max(0.0, -inward * sa, -inward * sb)
            if best is None or gap < best[1]:
                best = (vid, gap, out, Lv)
        print(f"{s} {wid:12s} L={L/1000:4.1f}  " + (f"koskee {best[0]} ({best[3]/1000:.0f} m) rako={best[1]:.0f} ulos={best[2]:.0f} mm" if best else "vapaa"))

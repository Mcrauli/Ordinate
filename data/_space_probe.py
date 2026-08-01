"""Missa tila on ja mika sita rajaa?"""
import json, sys
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon

out = Path(sys.argv[1])
m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
for s in m["spaces"]:
    b = np.array(s["boundary"], float)
    p = Polygon([(x, y) for x, y in b])
    r = list(p.minimum_rotated_rectangle.exterior.coords)
    e1 = np.hypot(r[1][0]-r[0][0], r[1][1]-r[0][1]); e2 = np.hypot(r[2][0]-r[1][0], r[2][1]-r[1][1])
    c = p.representative_point()
    near = []
    for w in m["walls"]:
        a0, a1 = np.array(w["axis"], float)
        d = a1 - a0; L = np.linalg.norm(d)
        if L < 1: continue
        u = d / L; n = np.array([-u[1], u[0]])
        dist = min(abs(float((np.array([x, y]) - a0) @ n)) for x, y in b)
        if dist < 400:
            near.append(f"{w['id']}(t{w['thickness']:.0f},{dist:.0f}mm)")
    print(f"{s['id']} ala={p.area/1e6:6.2f} m2  {min(e1,e2)/1000:.2f}x{max(e1,e2)/1000:.2f} m "
          f"@({c.x/1000:5.2f},{c.y/1000:5.2f}) conf={s['confidence']}")
    print(f"    rajaavat: {', '.join(near[:6]) or 'EI SEINIA'}")

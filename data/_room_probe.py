"""Miksi tila hylattiin? Listaa polygonize-kasvot ja kunkin hylkayssyyn.

Aja:  .venv\\Scripts\\python data/_room_probe.py data/output/_scale_s
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

from scan2bim.core.semantics import room_detector as rd

model = json.loads(sorted(Path(sys.argv[1]).glob("floor_*/model.json"))[0]
                   .read_text(encoding="utf-8"))

lines = []
for w in model["walls"]:
    p0, p1 = np.array(w["axis"], float)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    if L < 1.0:
        continue
    u = d / L
    a, b = p0 - rd._EXTEND * u, p1 + rd._EXTEND * u
    lines.append(LineString([tuple(a), tuple(b)]))

polys = sorted(polygonize(unary_union(lines)), key=lambda p: -p.area)
print(f"{len(polys)} kasvoa")
for i, p in enumerate(polys):
    a = p.area
    rect = p.minimum_rotated_rectangle
    rc = list(rect.exterior.coords)
    e1 = np.hypot(rc[1][0] - rc[0][0], rc[1][1] - rc[0][1])
    e2 = np.hypot(rc[2][0] - rc[1][0], rc[2][1] - rc[1][1])
    wdt, lng = min(e1, e2), max(e1, e2)
    asp = lng / wdt if wdt > 1 else 1e9
    inside = len(p.interiors)
    why = []
    if a < rd._MIN_AREA:
        why.append("MIN_AREA")
    if inside:
        why.append("ULKOKEHA(reikia)")
    if wdt < rd._MIN_WIDTH:
        why.append("MIN_WIDTH")
    if asp > rd._MAX_ASPECT and a < rd._ASPECT_AREA:
        why.append("ASPECT")
    c = p.representative_point()
    print(f"  {i:2d} ala={a/1e6:8.1f} m2  lev={wdt/1000:5.2f} m  asp={asp:5.1f}  "
          f"reikia={inside:2d}  @({c.x/1000:5.1f},{c.y/1000:5.1f})  "
          f"{'HYLKY: ' + ','.join(why) if why else 'OK'}")

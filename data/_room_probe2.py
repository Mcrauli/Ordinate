"""detect_rooms mallin seinilla + oikealla lattiakontuurilla: mika kasvo hylataan?"""
import json, sys
from pathlib import Path
import numpy as np
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union
from scan2bim.core.semantics import room_detector as rd
from scan2bim.schemas.model import ElementSource, Wall

out = Path(sys.argv[1])
m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
walls = [Wall(id=w["id"], confidence=w["confidence"], classification="wall",
              source=ElementSource(method=w["source"]["method"]), axis=w["axis"],
              height=w["height"], thickness=w["thickness"], z_min=w["z_min"])
         for w in m["walls"]]
ring = [(0.0, 0.0), (72000.0, 0.0), (72000.0, 48000.0), (0.0, 48000.0)]

print("ilman kontuuria:", len(rd.detect_rooms(walls, 0.0, 7000.0)))
sp = rd.detect_rooms(walls, 0.0, 7000.0, boundaries=[ring])
print("kontuurin kanssa:", len(sp))

lines = [LineString([*ring, ring[0]])]
for w in walls:
    p0, p1 = np.array(w.axis, float)
    d = p1 - p0; L = np.linalg.norm(d)
    if L < 1: continue
    u = d / L
    lines.append(LineString([tuple(p0 - rd._EXTEND * u), tuple(p1 + rd._EXTEND * u)]))
polys = sorted(polygonize(unary_union(lines)), key=lambda p: -p.area)
print(f"{len(polys)} kasvoa:")
for i, p in enumerate(polys[:12]):
    r = p.minimum_rotated_rectangle.exterior.coords[:]
    e1 = np.hypot(r[1][0]-r[0][0], r[1][1]-r[0][1]); e2 = np.hypot(r[2][0]-r[1][0], r[2][1]-r[1][1])
    wd = min(e1, e2); asp = max(e1, e2)/wd if wd > 1 else 1e9
    why = []
    if p.area < rd._MIN_AREA: why.append("MIN_AREA")
    if len(p.interiors): why.append(f"REIKIA({len(p.interiors)})")
    if wd < rd._MIN_WIDTH: why.append("MIN_WIDTH")
    if asp > rd._MAX_ASPECT and p.area < rd._ASPECT_AREA: why.append("ASPECT")
    c = p.representative_point()
    print(f"  {i:2d} ala={p.area/1e6:8.1f} m2 lev={wd/1000:6.2f} asp={asp:6.1f} "
          f"@({c.x/1000:5.1f},{c.y/1000:5.1f}) {','.join(why) or 'OK'}")

import json, numpy as np, sys
sys.path.insert(0, "src")
from scan2bim.schemas.model import Wall

m = json.load(open("data/output/apt_v29/model.json"))
walls_data = m["walls"]

# Reconstruct Wall objects to simulate snap_corners input (before second pass)
# Let's just test: given current wall_105 and wall_000, does snap_corners fix the gap?
from scan2bim.core.semantics.corner_snap import snap_corners, _try_connect

walls = []
for w in walls_data:
    walls.append(Wall(**w))

print("BEFORE snap_corners:")
for w in walls:
    if "105" in w.id or "000" in w.id:
        print(f"  {w.id}: p0={w.axis[0]} p1={w.axis[1]}")

result = snap_corners(walls)

print("AFTER snap_corners:")
for w in result:
    if "105" in w.id or "000" in w.id:
        print(f"  {w.id}: p0={w.axis[0]} p1={w.axis[1]}")

# Check gap
w105 = next(w for w in result if "105" in w.id)
w000 = next(w for w in result if "000" in w.id)
import math
gap = math.dist(w105.axis[1], w000.axis[0])
print(f"\ngap wall_105[1] ~ wall_000[0] = {gap:.1f}mm")

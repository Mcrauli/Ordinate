"""detect_rooms mallin seinilla + OIKEALLA lasketulla lattiakontuurilla."""
import json, sys
from pathlib import Path
import numpy as np, open3d as o3d
from shapely.geometry import Polygon
from scan2bim.core.segmentation.slab_detector import detect_floor_contours
from scan2bim.core.semantics import room_detector as rd
from scan2bim.schemas.model import ElementSource, Wall

cloud_path, out = Path(sys.argv[1]), Path(sys.argv[2])
m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
walls = [Wall(id=w["id"], confidence=w["confidence"], classification="wall",
              source=ElementSource(method=w["source"]["method"]), axis=w["axis"],
              height=w["height"], thickness=w["thickness"], z_min=w["z_min"])
         for w in m["walls"]]
floor = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
ceil = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=None)
pc = o3d.io.read_point_cloud(str(cloud_path)).voxel_down_sample(25.0)
cs = detect_floor_contours(pc, floor, ceiling_elevation=ceil, walls=walls)
print(f"kontuureja {len(cs)}; karkia {[len(c) for c in cs]}")
p = Polygon([(float(x), float(y)) for x, y in cs[0]])
print("kontuuri:", [(round(x), round(y)) for x, y in cs[0]], f"ala {p.area/1e6:.0f} m2")
sp = rd.detect_rooms(walls, floor, ceil or 7000.0, boundaries=cs)
print("tiloja:", len(sp))
for s in sp:
    b = np.array(s.boundary, float); x, y = b[:, 0], b[:, 1]
    print("  ", s.id, round(abs(np.dot(x, np.roll(y,-1))-np.dot(y, np.roll(x,-1)))/2/1e6, 1), "m2")

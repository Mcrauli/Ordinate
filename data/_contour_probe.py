"""Mita detect_floor_contours oikeasti palauttaa talle skannille?

Aja: .venv\\Scripts\\python data/_contour_probe.py data/_retail_s.ply data/output/_scale_s4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d
from shapely.geometry import Polygon

from scan2bim.core.segmentation.slab_detector import detect_floor_contours
from scan2bim.schemas.model import ElementSource, Wall

cloud_path, out = Path(sys.argv[1]), Path(sys.argv[2])
m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
walls = [Wall(id=w["id"], confidence=w["confidence"], classification="wall",
              source=ElementSource(method=w["source"]["method"]), axis=w["axis"],
              height=w["height"], thickness=w["thickness"], z_min=w["z_min"])
         for w in m["walls"]]
floor = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
ceil = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=None)

pc = o3d.io.read_point_cloud(str(cloud_path))
pc = pc.voxel_down_sample(25.0)
print(f"pilvi {len(pc.points):,} pistetta (25 mm), lattia {floor:.0f} katto {ceil}")

for label, ws in (("seinat mukana", walls), ("ILMAN seinia", None)):
    cs = detect_floor_contours(pc, floor, ceiling_elevation=ceil, walls=ws)
    print(f"\n--- {label}: {len(cs)} kontuuria ---")
    for i, c in enumerate(cs[:12]):
        p = Polygon([(float(x), float(y)) for x, y in c])
        b = np.array(c, float)
        print(f"  {i:2d} ala={p.area/1e6:8.1f} m2  karkia={len(c):3d}  valid={p.is_valid}  "
              f"bbox=({b[:,0].min()/1000:.0f},{b[:,1].min()/1000:.0f})-"
              f"({b[:,0].max()/1000:.0f},{b[:,1].max()/1000:.0f})")

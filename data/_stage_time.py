"""Missa geometriaketjun aika oikeasti menee? Ajaa yksittaiset vaiheet valmiilla
mallilla + oikealla pilvella ja kellottaa ne erikseen.

Ilman tata "Pintalukitus 1436 s" on vain vali kahden progress-viestin valissa,
ei tieto siita mika sen sisalla maksaa.

Aja: .venv\\Scripts\\python data/_stage_time.py data/_retail_l.ply data/output/_scale_l
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d

from ordinate.core import pipeline as pl
from ordinate.core.geometry.loader import ply_z_range, read_ply_xyz_band
from ordinate.schemas.model import ElementSource, Wall

cloud_path, out = Path(sys.argv[1]), Path(sys.argv[2])
m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
walls = [Wall(id=w["id"], confidence=w["confidence"], classification="wall",
              source=ElementSource(method=w["source"]["method"]), axis=w["axis"],
              height=w["height"], thickness=w["thickness"], z_min=w["z_min"])
         for w in m["walls"]]

zr = ply_z_range(cloud_path)
z0 = zr[0] + 0.35 * (zr[1] - zr[0])
z1 = zr[0] + 0.65 * (zr[1] - zr[0])
t = time.time()
thick = read_ply_xyz_band(cloud_path, z0, z1, max_points=45_000_000)
print(f"lataus            {time.time()-t:7.1f}s  {len(thick):,} pistetta, {len(walls)} seinaa")

pc = o3d.geometry.PointCloud()
pc.points = o3d.utility.Vector3dVector(thick)

t = time.time()
pl._thickness_lock_walls(walls, pc)
print(f"_thickness_lock   {time.time()-t:7.1f}s  (3 iteraatiota)")

t = time.time()
pl._align_faces_to_surface_median(walls, pc)
print(f"_align_faces      {time.time()-t:7.1f}s")

t = time.time()
pl._recenter_wall_axes(walls, pc)
print(f"_recenter_axes    {time.time()-t:7.1f}s")

t = time.time()
pl._snap_delivery_thickness(walls, pc)
print(f"_snap_delivery    {time.time()-t:7.1f}s")

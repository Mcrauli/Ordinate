"""Aja _thickness_lock_wall yhdelle seinalle ja kerro MITEN paksuus syntyi.

Aja: .venv\\Scripts\\python data/_tl_probe.py data/_retail_s.ply data/output/_scale_s2 wall_081
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

from ordinate.core import pipeline as pl
from ordinate.core.geometry.loader import ply_z_range, read_ply_xyz_band
from ordinate.schemas.model import ElementSource, Wall

cloud, out, wid = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
w = next(x for x in m["walls"] if x["id"] == wid)

zr = ply_z_range(cloud)
z0 = zr[0] + 0.35 * (zr[1] - zr[0])
z1 = zr[0] + 0.65 * (zr[1] - zr[0])
pts = read_ply_xyz_band(cloud, z0, z1, max_points=45_000_000)
print(f"thick-kaista {len(pts):,} pistetta, z {z0:.0f}..{z1:.0f}")

wall = Wall(id=wid, confidence=1.0, classification="wall",
            source=ElementSource(method="contour"), axis=w["axis"],
            height=w["height"], thickness=w["thickness"], z_min=w["z_min"])

p0 = np.array(wall.axis[0], float)
p1 = np.array(wall.axis[1], float)
L = float(np.linalg.norm(p1 - p0))
along = (p1 - p0) / L
normal = np.array([-along[1], along[0]])
axis_D = float(np.dot(normal, p0))
ap = (pts[:, :2] - p0) @ along
dist = pts[:, :2] @ normal - axis_D
mask = ((ap >= -pl._TL_ALONG_MARGIN) & (ap <= L + pl._TL_ALONG_MARGIN)
        & (np.abs(dist) <= pl._TL_SEARCH)
        & (pts[:, 2] >= wall.z_min + 200.0)
        & (pts[:, 2] <= wall.z_min + wall.height - 200.0))
print(f"kaistassa {int(mask.sum()):,} pistetta (min {pl._TL_MIN_PTS})")

d = dist[mask]
edges = np.arange(-pl._TL_SEARCH, pl._TL_SEARCH + pl._TL_BIN, pl._TL_BIN)
hist, edges = np.histogram(d, bins=edges)
centers = 0.5 * (edges[:-1] + edges[1:])
pks, _ = find_peaks(hist, height=hist.max() * pl._TL_PEAK_FRAC,
                    distance=int(20.0 / pl._TL_BIN))
print(f"huiput >=25% ({hist.max()*0.25:.0f}): "
      + ", ".join(f"{centers[p]:+.1f}mm x{hist[p]}" for p in pks))
weak, _ = find_peaks(hist, height=hist.max() * pl._TL_WEAK_FRAC,
                     distance=int(20.0 / pl._TL_BIN))
print(f"heikot >=8%: " + ", ".join(f"{centers[p]:+.1f}mm x{hist[p]}" for p in weak))

inside = pts[:, :2].mean(axis=0)
res = pl._thickness_lock_wall(wall, pts, None, inside)
print(f"ENNEN  akseli={wall.axis[0]} t={wall.thickness}")
print(f"JALKEEN akseli={res.axis[0]} t={res.thickness}")

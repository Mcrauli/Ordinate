"""Raakapisteiden poikkileikkaushistogrammi yhden seinan kohdalta.

Kertoo onko seinalla oikeasti kaksi pintaa vai onko "paksuus" keksitty.

Aja: .venv\\Scripts\\python data/_face_hist.py data/_retail_s.ply wall_081 data/output/_scale_s
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from scan2bim.core.geometry.loader import ply_z_range, read_ply_xyz_band

cloud = Path(sys.argv[1])
wid = sys.argv[2]
out = Path(sys.argv[3])

m = json.loads(sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8"))
w = next(x for x in m["walls"] if x["id"] == wid)
p0, p1 = np.array(w["axis"], float)
u = (p1 - p0) / np.linalg.norm(p1 - p0)
n = np.array([-u[1], u[0]])

zr = ply_z_range(cloud)
z0 = zr[0] + 0.35 * (zr[1] - zr[0])
z1 = zr[0] + 0.65 * (zr[1] - zr[0])
pts = read_ply_xyz_band(cloud, z0, z1, max_points=20_000_000)
print(f"kaista z {z0:.0f}..{z1:.0f}  {len(pts):,} pistetta")

rel = pts[:, :2] - p0
s = rel @ u
d = rel @ n
L = float(np.linalg.norm(p1 - p0))
sel = (s > 0.15 * L) & (s < 0.85 * L) & (np.abs(d) < 600.0)
dd = d[sel]
print(f"seinan {wid}: L={L:.0f} t={w['thickness']} mit={w.get('measured_thickness')} "
      f"kaistassa {len(dd):,} pistetta")
hist, edges = np.histogram(dd, bins=np.arange(-600, 601, 10.0))
for h, e in zip(hist, edges):
    if h:
        print(f"  {e:+7.0f} mm  {h:8d}  {'#' * min(60, h // max(1, hist.max() // 60))}")

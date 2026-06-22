"""
Generoi synteettinen testihuone PLY-muodossa.
Huone: 6000 x 4000 x 2800 mm, 4 seinää, lattia, katto.
Pisteet ovat 20 mm välein + normaalijakauman kohina ±5 mm.

Käyttö:
    cd C:/Users/lauri/scan2bim
    .venv/Scripts/python data/create_test_cloud.py
    → data/raw/test_room.ply
"""
import numpy as np
import open3d as o3d
from pathlib import Path

rng = np.random.default_rng(42)

W, D, H = 6000.0, 4000.0, 2800.0  # mm
STEP = 20.0
NOISE = 5.0

def wall_pts(x0, y0, x1, y1, z0=0.0, z1=H):
    """Pisteet yhdelle seinäpinnalle."""
    length = np.hypot(x1 - x0, y1 - y0)
    n_len = max(int(length / STEP), 2)
    n_z = max(int((z1 - z0) / STEP), 2)
    t = np.linspace(0, 1, n_len)
    z = np.linspace(z0, z1, n_z)
    tt, zz = np.meshgrid(t, z)
    xs = x0 + tt * (x1 - x0)
    ys = y0 + tt * (y1 - y0)
    pts = np.stack([xs.ravel(), ys.ravel(), zz.ravel()], axis=1)
    pts += rng.normal(0, NOISE, pts.shape)
    return pts

def slab_pts(z):
    """Pisteet yhdelle vaakatasopinnalle."""
    xs = np.arange(0, W, STEP)
    ys = np.arange(0, D, STEP)
    xx, yy = np.meshgrid(xs, ys)
    zz = np.full_like(xx, z)
    pts = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)
    pts += rng.normal(0, NOISE, pts.shape)
    return pts

pts = np.concatenate([
    wall_pts(0, 0, W, 0),      # eteläseinä
    wall_pts(W, 0, W, D),      # itäseinä
    wall_pts(W, D, 0, D),      # pohjoisseinä
    wall_pts(0, D, 0, 0),      # länsiseinä
    slab_pts(0),               # lattia
    slab_pts(H),               # katto
], axis=0)

cloud = o3d.geometry.PointCloud()
cloud.points = o3d.utility.Vector3dVector(pts)

out = Path(__file__).parent / "raw" / "test_room.ply"
out.parent.mkdir(parents=True, exist_ok=True)
o3d.io.write_point_cloud(str(out), cloud)
print(f"Kirjoitettu: {out}  ({len(pts):,} pistettä)")

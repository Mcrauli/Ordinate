"""
Synteettinen rakennus: 3 huonetta, käytävä, 4 pilaria, epätäydelliset seinät, realistinen kohina.
Yksikkö: mm. Skannaus simuloitu — seinistä vain yksi pinta näkyy (sisäpuoli).

Käyttö:
    .venv\Scripts\python data\create_building.py
    → data/raw/building.ply
"""
import numpy as np
import open3d as o3d
from pathlib import Path

rng = np.random.default_rng(7)
STEP = 25.0     # mm pisteiden välillä
NOISE = 8.0     # mm normaalijakauman kohina
H = 3200.0      # huonekorkeus mm

def surface(x0, y0, x1, y1, z0=0.0, z1=H, density=STEP, coverage=0.85):
    """Yksi seinäpinta pisteinä. coverage < 1 = reikäinen (ikkuna/ovi/occlusion)."""
    length = np.hypot(x1 - x0, y1 - y0)
    n_len = max(int(length / density), 2)
    n_z = max(int((z1 - z0) / density), 2)
    t = np.linspace(0, 1, n_len)
    z = np.linspace(z0, z1, n_z)
    tt, zz = np.meshgrid(t, z)
    xs = x0 + tt * (x1 - x0)
    ys = y0 + tt * (y1 - y0)
    pts = np.stack([xs.ravel(), ys.ravel(), zz.ravel()], axis=1)
    # satunnainen peitto (ikkuna/occlusion)
    mask = rng.random(len(pts)) < coverage
    pts = pts[mask]
    pts += rng.normal(0, NOISE, pts.shape)
    return pts

def slab(x0, y0, x1, y1, z, density=STEP):
    xs = np.arange(x0, x1, density)
    ys = np.arange(y0, y1, density)
    xx, yy = np.meshgrid(xs, ys)
    zz = np.full_like(xx, z, dtype=float)
    pts = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)
    pts += rng.normal(0, NOISE, pts.shape)
    return pts

def column(cx, cy, size=300.0, n_pts=200):
    """Pyöreä pilari."""
    angles = rng.uniform(0, 2 * np.pi, n_pts)
    zs = rng.uniform(0, H, n_pts)
    r = size / 2
    xs = cx + r * np.cos(angles) + rng.normal(0, NOISE, n_pts)
    ys = cy + r * np.sin(angles) + rng.normal(0, NOISE, n_pts)
    return np.stack([xs, ys, zs], axis=1)

# --- layout (mm) ---
# Ulkoseinät: 18000 x 12000
# Huone A: 0–6000 x 0–8000
# Huone B: 6000–12000 x 0–8000
# Huone C: 12000–18000 x 0–8000
# Käytävä: 0–18000 x 8000–12000

parts = []

# Ulkoseinät
parts += [
    surface(0, 0, 18000, 0),           # eteläseinä
    surface(18000, 0, 18000, 12000),    # itäseinä
    surface(18000, 12000, 0, 12000),    # pohjoisseinä
    surface(0, 12000, 0, 0),           # länsiseinä
]

# Väliseinät (ei lattia–katto, reikiä ovista)
parts += [
    surface(6000, 0, 6000, 8000, coverage=0.7),    # AB-väliseinä (ovi)
    surface(12000, 0, 12000, 8000, coverage=0.7),   # BC-väliseinä (ovi)
    surface(0, 8000, 18000, 8000, coverage=0.75),   # käytävän seinä (useita ovia)
]

# Lattia ja katto
parts += [
    slab(0, 0, 18000, 12000, 0),
    slab(0, 0, 18000, 12000, H),
]

# Pilarit käytävällä
for px, py in [(3000, 10000), (9000, 10000), (15000, 10000), (9000, 4000)]:
    parts.append(column(px, py))

# Pieni kohina / krääsä (huonekalut jne.)
clutter_x = rng.uniform(500, 17500, 800)
clutter_y = rng.uniform(500, 7500, 800)
clutter_z = rng.uniform(0, 1200, 800)
parts.append(np.stack([clutter_x, clutter_y, clutter_z], axis=1))

pts = np.concatenate(parts, axis=0)
cloud = o3d.geometry.PointCloud()
cloud.points = o3d.utility.Vector3dVector(pts)

out = Path(__file__).parent / "raw" / "building.ply"
o3d.io.write_point_cloud(str(out), cloud)
print(f"Kirjoitettu: {out}  ({len(pts):,} pistettä)")
print(f"Huoneet A/B/C + käytävä, 4 pilaria, reikiä ovista, krääsää")

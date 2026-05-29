"""WallDetector-testit synteettisellä pistepilvellä.

Synteettinen huone: 4 seinää (pohjapiirros 6000 x 4000 mm, korkeus 2800 mm).
Jokainen seinä on tasainen suorakaiteen muotoinen pistepilvi +/- 5 mm kohinalla.
"""
from __future__ import annotations

import numpy as np
import pytest
import open3d as o3d

from scan2bim.core.segmentation.wall_detector import WallDetector
from scan2bim.schemas.model import Wall


# --------------------------------------------------------------------------- #
# Apufunktio synteettisen huoneen luomiseen
# --------------------------------------------------------------------------- #

def _make_room_cloud(
    width: float = 6000.0,    # mm X
    depth: float = 4000.0,    # mm Y
    height: float = 2800.0,   # mm Z
    density: int = 40,        # pistettä per metri seinää
    noise_mm: float = 5.0,
    rng: np.random.Generator | None = None,
) -> o3d.geometry.PointCloud:
    """Luo yksinkertaisen suorakulmaisen huoneen pistepilvi."""
    if rng is None:
        rng = np.random.default_rng(42)

    pts_per_m = density
    walls_pts = []

    def wall_pts(fixed_axis, fixed_val, vary_lo, vary_hi, z_hi, n):
        u = rng.uniform(vary_lo, vary_hi, n)
        z = rng.uniform(0, z_hi, n)
        noise = rng.normal(0, noise_mm, n)
        if fixed_axis == 0:  # X fixed → YZ wall
            return np.column_stack([np.full(n, fixed_val) + noise, u, z])
        else:                 # Y fixed → XZ wall
            return np.column_stack([u, np.full(n, fixed_val) + noise, z])

    n_long = int(width / 1000 * pts_per_m * height / 1000 * pts_per_m)
    n_short = int(depth / 1000 * pts_per_m * height / 1000 * pts_per_m)

    walls_pts.append(wall_pts(1, 0.0,    0.0, width, height, n_long))   # Y=0
    walls_pts.append(wall_pts(1, depth,  0.0, width, height, n_long))   # Y=depth
    walls_pts.append(wall_pts(0, 0.0,    0.0, depth, height, n_short))  # X=0
    walls_pts.append(wall_pts(0, width,  0.0, depth, height, n_short))  # X=width

    all_pts = np.vstack(walls_pts)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(all_pts.astype(np.float64))
    return cloud


# --------------------------------------------------------------------------- #
# Testit
# --------------------------------------------------------------------------- #

def test_detect_returns_walls():
    cloud = _make_room_cloud()
    detector = WallDetector(distance_threshold=20.0)
    walls = detector.detect(cloud)
    assert len(walls) > 0, "Pitäisi löytää ainakin yksi seinä"


def test_detect_finds_four_walls():
    cloud = _make_room_cloud()
    detector = WallDetector(distance_threshold=20.0, num_iterations=500)
    walls = detector.detect(cloud)
    assert len(walls) == 4, f"Odotettiin 4 seinää, löytyi {len(walls)}"


def test_wall_types():
    cloud = _make_room_cloud()
    detector = WallDetector(distance_threshold=20.0)
    walls = detector.detect(cloud)
    for w in walls:
        assert isinstance(w, Wall)
        assert 0.0 <= w.confidence <= 1.0
        assert w.height > 400.0, "Korkeus liian pieni"
        assert w.thickness > 0.0
        assert len(w.axis) == 2
        assert len(w.axis[0]) == 2


def test_wall_dimensions_approx():
    """Pitkien seinien pituus lähellä room width/depth."""
    width, depth, height = 6000.0, 4000.0, 2800.0
    cloud = _make_room_cloud(width=width, depth=depth, height=height)
    detector = WallDetector(distance_threshold=20.0)
    walls = detector.detect(cloud)

    lengths = []
    for w in walls:
        p0, p1 = np.array(w.axis[0]), np.array(w.axis[1])
        lengths.append(float(np.linalg.norm(p1 - p0)))

    long_walls = [l for l in lengths if abs(l - width) < 200]
    short_walls = [l for l in lengths if abs(l - depth) < 200]
    assert len(long_walls) >= 2, f"Pitäisi olla 2 pitkää seinää (~{width}mm), löytyi: {lengths}"
    assert len(short_walls) >= 2, f"Pitäisi olla 2 lyhyttä seinää (~{depth}mm), löytyi: {lengths}"


def test_wall_height_approx():
    height = 2800.0
    cloud = _make_room_cloud(height=height)
    detector = WallDetector(distance_threshold=20.0)
    walls = detector.detect(cloud)
    for w in walls:
        assert abs(w.height - height) < 200, f"Korkeus {w.height} ei lähellä {height}"


def test_noisy_cloud_still_finds_walls():
    """Paljon kohinaa (15 mm) → löytyy silti seinät."""
    cloud = _make_room_cloud(noise_mm=15.0, rng=np.random.default_rng(7))
    detector = WallDetector(distance_threshold=30.0)
    walls = detector.detect(cloud)
    assert len(walls) >= 3, f"Meluisesta pilvistä pitäisi löytyä ≥3 seinää, löytyi {len(walls)}"


def test_empty_cloud_returns_empty():
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
    detector = WallDetector()
    walls = detector.detect(cloud)
    assert walls == []

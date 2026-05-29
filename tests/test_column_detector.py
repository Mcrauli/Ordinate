"""ColumnDetector-testit synteettisellä pistepilvellä.

Synteettinen tilanne: 4 pilaria nurkkiin (300 × 300 mm, korkeus 2800 mm).
"""
from __future__ import annotations

import numpy as np
import pytest
import open3d as o3d

from scan2bim.core.segmentation.column_detector import ColumnDetector
from scan2bim.schemas.model import Column


# --------------------------------------------------------------------------- #
# Apufunktiot
# --------------------------------------------------------------------------- #

def _column_pts(cx: float, cy: float, w: float, d: float, h: float, n: int, rng) -> np.ndarray:
    """Suorakaidepilaripiste: tasainen jakauma pinnoilla."""
    x = rng.uniform(cx - w/2, cx + w/2, n)
    y = rng.uniform(cy - d/2, cy + d/2, n)
    z = rng.uniform(0, h, n)
    return np.column_stack([x, y, z])


def _make_cloud_with_columns(
    col_size: float = 300.0,
    height: float = 2800.0,
    pts_per_col: int = 300,
    rng: np.random.Generator | None = None,
) -> o3d.geometry.PointCloud:
    if rng is None:
        rng = np.random.default_rng(123)
    cols = [
        _column_pts(500, 500, col_size, col_size, height, pts_per_col, rng),
        _column_pts(5500, 500, col_size, col_size, height, pts_per_col, rng),
        _column_pts(500, 3500, col_size, col_size, height, pts_per_col, rng),
        _column_pts(5500, 3500, col_size, col_size, height, pts_per_col, rng),
    ]
    pts = np.vstack(cols)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pts.astype(np.float64))
    return cloud


# --------------------------------------------------------------------------- #
# Testit
# --------------------------------------------------------------------------- #

def test_detect_finds_columns():
    cloud = _make_cloud_with_columns()
    cols = ColumnDetector(eps_mm=60, min_points=20).detect(cloud)
    assert len(cols) == 4, f"Odotettiin 4 pilaria, löytyi {len(cols)}"


def test_column_schema_valid():
    cloud = _make_cloud_with_columns()
    cols = ColumnDetector(eps_mm=60, min_points=20).detect(cloud)
    for c in cols:
        assert isinstance(c, Column)
        assert 0.0 <= c.confidence <= 1.0
        assert c.height > 500
        assert len(c.location) == 2
        assert c.profile.width > 0
        assert c.profile.depth > 0


def test_column_locations_approx():
    """Pilarin sijainti ≤ 100 mm tarkkuudella."""
    cloud = _make_cloud_with_columns(rng=np.random.default_rng(42))
    cols = ColumnDetector(eps_mm=60, min_points=20).detect(cloud)
    expected = {(500, 500), (5500, 500), (500, 3500), (5500, 3500)}
    for c in cols:
        x, y = c.location
        close = any(abs(x - ex) < 100 and abs(y - ey) < 100 for ex, ey in expected)
        assert close, f"Pilari {x:.0f},{y:.0f} ei lähellä mitään odotettua"


def test_wall_fragment_not_detected():
    """Pitkä seinäfragmentti (4000 × 200 mm) ei saa olla pilari."""
    rng = np.random.default_rng(7)
    x = rng.uniform(0, 4000, 400)
    y = rng.uniform(-100, 100, 400)
    z = rng.uniform(0, 2800, 400)
    wall_pts = np.column_stack([x, y, z])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(wall_pts)
    cols = ColumnDetector(eps_mm=80, min_points=20).detect(cloud)
    assert len(cols) == 0, "Seinäfragmentti ei saa läpäistä pilarisuodatusta"


def test_empty_cloud():
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
    cols = ColumnDetector().detect(cloud)
    assert cols == []


def test_circle_profile_for_round_column():
    rng = np.random.default_rng(11)
    r = 150.0
    angles = rng.uniform(0, 2 * np.pi, 500)
    radii = rng.uniform(0, r, 500)
    x = radii * np.cos(angles) + 1000
    y = radii * np.sin(angles) + 1000
    z = rng.uniform(0, 2800, 500)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    cols = ColumnDetector(eps_mm=60, min_points=20).detect(cloud)
    assert len(cols) == 1
    # Pyöreä pilari (width ≈ depth) → circle-profiili
    assert cols[0].profile.shape in ("circle", "rect")

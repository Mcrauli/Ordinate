"""SlabDetector-testit synteettisellä pistepilvellä.

Synteettinen huone: lattia z=0, katto z=2800mm, seinät välissä.
"""
from __future__ import annotations

import numpy as np
import pytest
import open3d as o3d

from scan2bim.core.segmentation.slab_detector import SlabDetector
from scan2bim.schemas.model import Slab


# --------------------------------------------------------------------------- #
# Apufunktio
# --------------------------------------------------------------------------- #

def _make_room_cloud(
    width: float = 6000.0,
    depth: float = 4000.0,
    floor_z: float = 0.0,
    ceiling_z: float = 2800.0,
    noise_mm: float = 5.0,
    density: int = 30,
    rng: np.random.Generator | None = None,
) -> o3d.geometry.PointCloud:
    if rng is None:
        rng = np.random.default_rng(99)

    n = int(width / 1000 * density) * int(depth / 1000 * density)

    def flat_pts(z_center):
        x = rng.uniform(0, width, n)
        y = rng.uniform(0, depth, n)
        z = np.full(n, z_center) + rng.normal(0, noise_mm, n)
        return np.column_stack([x, y, z])

    # Seinäpisteet levitetty koko korkeudelle → eivät muodosta z-piikkiä
    n_wall = n // 2
    wx = rng.uniform(0, width, n_wall)
    wy = rng.uniform(0, depth, n_wall)
    wz = rng.uniform(floor_z, ceiling_z, n_wall)
    wall_pts = np.column_stack([wx, wy, wz])

    all_pts = np.vstack([flat_pts(floor_z), flat_pts(ceiling_z), wall_pts])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(all_pts)
    return cloud


# --------------------------------------------------------------------------- #
# Testit
# --------------------------------------------------------------------------- #

def test_detect_returns_slabs():
    cloud = _make_room_cloud()
    slabs, _ = SlabDetector().detect(cloud)
    assert len(slabs) > 0


def test_detect_finds_floor_and_ceiling():
    cloud = _make_room_cloud()
    slabs, _ = SlabDetector().detect(cloud)
    assert len(slabs) == 2, f"Odotettiin 2 laattaa, löytyi {len(slabs)}"


def test_slab_types():
    cloud = _make_room_cloud()
    slabs, _ = SlabDetector().detect(cloud)
    types = {s.slab_type for s in slabs}
    assert "floor" in types
    assert "ceiling" in types


def test_slab_elevations():
    floor_z, ceiling_z = 0.0, 2800.0
    cloud = _make_room_cloud(floor_z=floor_z, ceiling_z=ceiling_z)
    slabs, _ = SlabDetector().detect(cloud)
    elevations = sorted(s.elevation for s in slabs)
    assert abs(elevations[0] - floor_z) < 100, f"Lattia z={elevations[0]:.0f}, odotettiin ~{floor_z}"
    assert abs(elevations[-1] - ceiling_z) < 100, f"Katto z={elevations[-1]:.0f}, odotettiin ~{ceiling_z}"


def test_slab_boundary_is_closed():
    cloud = _make_room_cloud()
    slabs, _ = SlabDetector().detect(cloud)
    for s in slabs:
        assert len(s.boundary) >= 4
        assert s.boundary[0] == s.boundary[-1], "Polygonin pitää olla suljettu"


def test_slab_schema_valid():
    cloud = _make_room_cloud()
    slabs, _ = SlabDetector().detect(cloud)
    for s in slabs:
        assert isinstance(s, Slab)
        assert 0.0 <= s.confidence <= 1.0
        assert s.thickness > 0


def test_empty_cloud_returns_empty():
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
    slabs, _ = SlabDetector().detect(cloud)
    assert slabs == []


def test_noisy_cloud_finds_slabs():
    cloud = _make_room_cloud(noise_mm=12.0, rng=np.random.default_rng(55))
    slabs, _ = SlabDetector(z_band_mm=60.0).detect(cloud)
    assert len(slabs) >= 1

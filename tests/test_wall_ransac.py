"""RANSAC-seinädetektio — synteettinen huonepilvi (M4a)."""
import numpy as np
import open3d as o3d
import pytest

from ordinate.core.segmentation.base import DetectorRegistry
from ordinate.core.segmentation.wall_ransac import WallDetectorRANSAC
from ordinate.schemas.model import StructuralModel


def _box_room_cloud(seed: int = 0) -> o3d.geometry.PointCloud:
    rng = np.random.default_rng(seed)
    pts = []
    n = 500
    for _ in range(n):
        pts.append([5000, rng.uniform(0, 4000), rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([0, rng.uniform(0, 4000), rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), 4000, rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), 0, rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), rng.uniform(0, 4000), 0])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), rng.uniform(0, 4000), 2800])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(pts, dtype=np.float64))
    return cloud


def test_ransac_finds_walls():
    cloud = _box_room_cloud()
    model = WallDetectorRANSAC(ransac_distance=50.0, min_plane_points=50).detect(cloud)
    assert len(model.walls) >= 3


def test_ransac_returns_structural_model():
    cloud = _box_room_cloud()
    model = WallDetectorRANSAC().detect(cloud)
    assert isinstance(model, StructuralModel)


def test_ransac_wall_schema_valid():
    cloud = _box_room_cloud()
    model = WallDetectorRANSAC(ransac_distance=50.0, min_plane_points=50).detect(cloud)
    assert model.walls, "Ei yhtään seinää"
    for wall in model.walls:
        assert 0.0 <= wall.confidence <= 1.0
        assert wall.height > 0
        assert wall.thickness > 0
        assert len(wall.axis) == 2
        assert len(wall.axis[0]) == 2


def test_ransac_wall_height_matches_room():
    cloud = _box_room_cloud()
    model = WallDetectorRANSAC(ransac_distance=50.0, min_plane_points=50).detect(cloud)
    for wall in model.walls:
        assert 2000 < wall.height <= 3000


def test_registry_has_ransac():
    assert "ransac" in DetectorRegistry.names()
    assert DetectorRegistry.get("ransac") is WallDetectorRANSAC

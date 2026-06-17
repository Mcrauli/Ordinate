"""Density-seinädetektio — synteettinen huonepilvi (M4b)."""
import numpy as np
import open3d as o3d

from scan2bim.core.segmentation.base import DetectorRegistry
from scan2bim.core.segmentation.wall_density import WallDetectorDensity
from scan2bim.schemas.model import StructuralModel


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


def test_density_finds_walls():
    cloud = _box_room_cloud()
    model = WallDetectorDensity(grid_size=100.0, min_line_length=1000.0).detect(cloud)
    assert len(model.walls) >= 2


def test_density_returns_structural_model():
    cloud = _box_room_cloud()
    assert isinstance(WallDetectorDensity().detect(cloud), StructuralModel)


def test_density_wall_axis_in_bounds():
    cloud = _box_room_cloud()
    model = WallDetectorDensity(grid_size=100.0, min_line_length=500.0).detect(cloud)
    if not model.walls:
        return
    pts = np.asarray(cloud.points)
    x_lo, x_hi = float(pts[:, 0].min()) - 200, float(pts[:, 0].max()) + 200
    y_lo, y_hi = float(pts[:, 1].min()) - 200, float(pts[:, 1].max()) + 200
    for wall in model.walls:
        for px, py in wall.axis:
            assert x_lo <= px <= x_hi
            assert y_lo <= py <= y_hi


def test_density_wall_schema_valid():
    cloud = _box_room_cloud()
    model = WallDetectorDensity(grid_size=100.0, min_line_length=500.0).detect(cloud)
    for wall in model.walls:
        assert 0.0 <= wall.confidence <= 1.0
        assert wall.height > 0
        assert wall.thickness == 200.0


def test_registry_has_density():
    assert "density" in DetectorRegistry.names()
    assert DetectorRegistry.get("density") is WallDetectorDensity

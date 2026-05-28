"""Preprocessing-testit — normalisointi, downsample, kohinasuodatus."""
import numpy as np
import open3d as o3d
import pytest

from scan2bim.core.geometry.preprocess import preprocess, _normalize


def _box_room_cloud(seed: int = 0) -> o3d.geometry.PointCloud:
    """Synteettinen huone: 4 seinää + lattia + katto, 5 % kohinapisteitä."""
    rng = np.random.default_rng(seed)
    pts = []

    # 4 seinää (5000 x 2800 mm, ~500 pistettä kukin)
    n = 500
    for _ in range(n):  # seinä +X
        pts.append([5000, rng.uniform(0, 4000), rng.uniform(0, 2800)])
    for _ in range(n):  # seinä -X
        pts.append([0, rng.uniform(0, 4000), rng.uniform(0, 2800)])
    for _ in range(n):  # seinä +Y
        pts.append([rng.uniform(0, 5000), 4000, rng.uniform(0, 2800)])
    for _ in range(n):  # seinä -Y
        pts.append([rng.uniform(0, 5000), 0, rng.uniform(0, 2800)])
    # lattia + katto
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), rng.uniform(0, 4000), 0])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), rng.uniform(0, 4000), 2800])

    # 5 % kohinaa irrallisina klustereina
    n_noise = int(len(pts) * 0.05)
    noise_center = np.array([10000, 10000, 10000])
    noise = rng.normal(noise_center, 5, (n_noise, 3))
    pts.extend(noise.tolist())

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(pts, dtype=np.float64))
    return cloud


def test_normalize_shifts_to_origin():
    cloud = _box_room_cloud()
    normed = _normalize(cloud)
    pts = np.asarray(normed.points)
    assert pts.min(axis=0) == pytest.approx([0, 0, 0], abs=1.0)


def test_normalize_empty():
    cloud = o3d.geometry.PointCloud()
    result = _normalize(cloud)
    assert len(result.points) == 0


def test_voxel_downsample_reduces_count():
    cloud = _box_room_cloud()
    original_count = len(cloud.points)
    result = preprocess(cloud, voxel_size=100.0)
    assert len(result.points) < original_count


def test_outlier_removal_cleans_noise():
    cloud = _box_room_cloud()
    original_count = len(cloud.points)
    result = preprocess(cloud, voxel_size=30.0, std_ratio=1.5)
    # Irrallinen klusteri (10m päässä) pitäisi poistua
    pts = np.asarray(result.points)
    assert pts.max() < 8000, "Irrallinen kohinaklusteri ei poistunut"


def test_preprocess_returns_pointcloud():
    cloud = _box_room_cloud()
    result = preprocess(cloud, voxel_size=50.0)
    assert isinstance(result, o3d.geometry.PointCloud)
    assert len(result.points) > 0


def test_normalized_after_preprocess():
    cloud = _box_room_cloud()
    result = preprocess(cloud, voxel_size=50.0)
    pts = np.asarray(result.points)
    assert pts.min(axis=0) == pytest.approx([0, 0, 0], abs=60.0)

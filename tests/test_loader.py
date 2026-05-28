"""Loader-testit — käyttää synteettisiä tiedostoja, ei oikeaa pistepilveä."""
import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from scan2bim.core.geometry.loader import load_point_cloud


def _make_pts_file(tmp_path: Path, n: int = 100) -> Path:
    pts = tmp_path / "test.pts"
    rng = np.random.default_rng(42)
    xyz = rng.uniform(0, 5000, (n, 3))
    pts.write_text("\n".join(f"{x} {y} {z}" for x, y, z in xyz))
    return pts


def _make_ply_file(tmp_path: Path, n: int = 200) -> Path:
    ply = tmp_path / "test.ply"
    rng = np.random.default_rng(0)
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(rng.uniform(0, 5000, (n, 3)))
    o3d.io.write_point_cloud(str(ply), cloud)
    return ply


def test_load_pts(tmp_path):
    p = _make_pts_file(tmp_path, n=100)
    cloud = load_point_cloud(p)
    assert isinstance(cloud, o3d.geometry.PointCloud)
    assert len(cloud.points) == 100


def test_load_ply(tmp_path):
    p = _make_ply_file(tmp_path, n=200)
    cloud = load_point_cloud(p)
    assert len(cloud.points) == 200


def test_load_xyz(tmp_path):
    xyz_file = tmp_path / "test.xyz"
    rng = np.random.default_rng(1)
    pts = rng.uniform(0, 1000, (50, 3))
    xyz_file.write_text("\n".join(f"{x} {y} {z}" for x, y, z in pts))
    cloud = load_point_cloud(xyz_file)
    assert len(cloud.points) == 50


def test_unsupported_format(tmp_path):
    bad = tmp_path / "test.dwg"
    bad.write_text("junk")
    with pytest.raises(ValueError, match="Tuntematon formaatti"):
        load_point_cloud(bad)


def test_coordinates_preserved(tmp_path):
    p = _make_pts_file(tmp_path, n=10)
    raw = np.array([list(map(float, l.split())) for l in p.read_text().splitlines()])
    cloud = load_point_cloud(p)
    pts = np.asarray(cloud.points)
    np.testing.assert_allclose(pts, raw, atol=1e-3)

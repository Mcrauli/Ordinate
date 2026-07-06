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


def test_truncated_ply_warns_or_raises(tmp_path, caplog):
    """Katkennut lataus/siirto -> vajaa PLY: selkea varoitus (osittainen luku)
    tai selkovirhe (tyhja luku), ei aanetonta osittaista mallia."""
    import logging
    import numpy as np
    import open3d as o3d
    from scan2bim.core.geometry.loader import load_point_cloud

    pts = np.random.RandomState(0).uniform(0, 5000, (10000, 3))
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    full = tmp_path / "full.ply"
    o3d.io.write_point_cloud(str(full), pc)  # binaari-ply

    data = full.read_bytes()
    cut = tmp_path / "cut.ply"
    cut.write_bytes(data[: int(len(data) * 0.6)])   # katkaise 60 %:iin

    with caplog.at_level(logging.WARNING):
        try:
            cloud = load_point_cloud(cut)
        except ValueError as e:
            assert "vajaa" in str(e) or "vaurioitunut" in str(e)
            return
    assert any("vajaa" in r.message for r in caplog.records), \
        "vajaa tiedosto luettiin ilman varoitusta"
    assert len(cloud.points) < 10000

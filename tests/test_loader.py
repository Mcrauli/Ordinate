"""Loader-testit — käyttää synteettisiä tiedostoja, ei oikeaa pistepilveä."""
import tempfile
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from ordinate.core.geometry.loader import load_point_cloud


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


def _write_binary_ply(path: Path, xyz: np.ndarray) -> None:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz)
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False)


def test_read_ply_xyz_band_matches_full(tmp_path):
    """Lohkoluku antaa saman Z-kaistan kuin koko tiedoston luku + suodatus."""
    from ordinate.core.geometry.loader import read_ply_xyz_band
    rng = np.random.default_rng(3)
    xyz = rng.uniform(0, 10000, (50000, 3))
    p = tmp_path / "b.ply"
    _write_binary_ply(p, xyz)

    lo, hi = 3000.0, 6000.0
    # pieni chunk pakottaa monta lohkoa → testaa lohkorajat
    got = read_ply_xyz_band(p, lo, hi, chunk=7000)
    assert got is not None
    m = (xyz[:, 2] >= lo) & (xyz[:, 2] <= hi)
    exp = xyz[m]
    assert len(got) == len(exp)
    # järjestys säilyy → suora vertailu (o3d float32-tallennus → löysä tol)
    order_got = got[np.lexsort(got.T)]
    order_exp = exp[np.lexsort(exp.T)]
    np.testing.assert_allclose(order_got, order_exp, atol=0.5)


def test_read_ply_xyz_band_max_points(tmp_path):
    """max_points ohentaa kaistan kattoon satunnaisesti muttei siirrä jakaumaa."""
    from ordinate.core.geometry.loader import read_ply_xyz_band
    rng = np.random.default_rng(7)
    xyz = rng.uniform(0, 10000, (60000, 3))
    p = tmp_path / "m.ply"
    _write_binary_ply(p, xyz)
    lo, hi = 0.0, 10000.0
    full = read_ply_xyz_band(p, lo, hi)
    capped = read_ply_xyz_band(p, lo, hi, max_points=20000)
    assert len(full) == 60000
    # kattoraja = ENINTÄÄN max_points (satunnaisohennus → ~1 % alle, ei yli)
    assert 0.9 * 20000 <= len(capped) <= 20000
    # ohennus säilyttää jakauman keskikohdan (piikin paikka) — ei voxel-biasta
    assert abs(np.median(capped[:, 2]) - np.median(full[:, 2])) < 60.0


def test_read_ply_xyz_band_truncated(tmp_path):
    """Katkennut PLY: lohkoluku lukee roskattoman osan eikä kaadu."""
    from ordinate.core.geometry.loader import read_ply_xyz_band
    rng = np.random.default_rng(4)
    xyz = rng.uniform(0, 10000, (40000, 3))
    full = tmp_path / "f.ply"
    _write_binary_ply(full, xyz)
    data = full.read_bytes()
    cut = tmp_path / "c.ply"
    cut.write_bytes(data[: int(len(data) * 0.6)])
    got = read_ply_xyz_band(cut, 0.0, 10000.0, chunk=5000)
    assert got is not None
    assert 0 < len(got) < 40000


def test_ply_z_range_and_z(tmp_path):
    from ordinate.core.geometry.loader import ply_z_range, read_ply_z
    rng = np.random.default_rng(5)
    xyz = rng.uniform(-2000, 8000, (30000, 3))
    p = tmp_path / "z.ply"
    _write_binary_ply(p, xyz)
    rng_z = ply_z_range(p)
    assert rng_z is not None
    assert abs(rng_z[0] - xyz[:, 2].min()) < 1.0
    assert abs(rng_z[1] - xyz[:, 2].max()) < 1.0
    z = read_ply_z(p)
    assert z is not None and len(z) > 0


def test_ply_autoscale_factor_metres(tmp_path):
    """Metreissä oleva pilvi (laajuus < 200) → kerroin 1000."""
    from ordinate.core.geometry.loader import ply_autoscale_factor
    rng = np.random.default_rng(6)
    xyz_m = rng.uniform(0, 30, (5000, 3))   # metrit
    pm = tmp_path / "m.ply"
    _write_binary_ply(pm, xyz_m)
    assert ply_autoscale_factor(pm) == 1000.0
    xyz_mm = rng.uniform(0, 30000, (5000, 3))  # millimetrit
    pmm = tmp_path / "mm.ply"
    _write_binary_ply(pmm, xyz_mm)
    assert ply_autoscale_factor(pmm) == 1.0


def test_empty_pts_raises(tmp_path):
    """Tyhja/pisteeton PTS -> selkovirhe, ei aaneton tyhja pilvi."""
    p = tmp_path / "empty.pts"
    p.write_text("# vain kommentteja\nroskaa ei-numeroita\n")
    with pytest.raises(ValueError, match="piste"):
        load_point_cloud(p)


def test_corrupt_pts_warns(tmp_path, caplog):
    """Suuri osuus lukukelvottomia riveja -> varoitus (osittainen luku)."""
    import logging
    good = "\n".join(f"{x} {x} {x}" for x in range(50))
    bad = "\n".join("x y z" for _ in range(50))   # 50 lukukelvotonta
    p = tmp_path / "corrupt.pts"
    p.write_text(good + "\n" + bad)
    with caplog.at_level(logging.WARNING):
        cloud = load_point_cloud(p)
    assert len(cloud.points) == 50
    assert any("lukukelvot" in r.message for r in caplog.records)


def test_las_empty_or_truncated(tmp_path):
    """Katkennut LAS -> selkovirhe (vajaa/vaurioitunut), ei kryptista laspy-kaatoa."""
    laspy = pytest.importorskip("laspy")
    las = laspy.create(point_format=3)
    rng = np.random.default_rng(11)
    xyz = rng.uniform(0, 5000, (20000, 3))
    las.x, las.y, las.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    full = tmp_path / "full.las"
    las.write(str(full))
    data = full.read_bytes()
    cut = tmp_path / "cut.las"
    cut.write_bytes(data[: int(len(data) * 0.4)])   # katkaise 40 %:iin
    with pytest.raises(ValueError, match="vajaa|vaurioitunut|lukea"):
        load_point_cloud(cut)


def test_truncated_ply_warns_or_raises(tmp_path, caplog):
    """Katkennut lataus/siirto -> vajaa PLY: selkea varoitus (osittainen luku)
    tai selkovirhe (tyhja luku), ei aanetonta osittaista mallia."""
    import logging
    import numpy as np
    import open3d as o3d
    from ordinate.core.geometry.loader import load_point_cloud

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


def _floor_grid(x_m: float, y_m: float, step_m: float) -> np.ndarray:
    x = np.arange(0.0, x_m, step_m)
    y = np.arange(0.0, y_m, step_m)
    xx, yy = np.meshgrid(x, y)
    return np.column_stack([xx.ravel(), yy.ravel(), np.zeros(xx.size)])


def test_long_building_in_metres_is_still_scaled(tmp_path):
    """250 m halli metreissä: laajuus > 200 mutta kyse on metreistä.

    Pelkkä laajuussääntö sitoo yksikkötunnistuksen rakennuksen KOKOON ja jättää
    tämän skaalaamatta — putki näkisi 250 mm rakennuksen eikä valittaisi.
    Pisteväli (0.1) erottaa yksiköt koosta riippumatta.
    """
    from ordinate.core.geometry.loader import metre_scale, ply_autoscale_factor
    xyz = _floor_grid(250.0, 3.0, 0.1)
    assert np.ptp(xyz, axis=0).max() > 200.0
    assert metre_scale(xyz) == 1000.0
    p = tmp_path / "hall_m.ply"
    _write_binary_ply(p, xyz)
    assert ply_autoscale_factor(p) == 1000.0


def test_large_building_in_millimetres_is_not_scaled(tmp_path):
    """Sama halli millimetreinä pysyy millimetreinä — pisteväli 100 mm."""
    from ordinate.core.geometry.loader import metre_scale
    assert metre_scale(_floor_grid(250_000.0, 3000.0, 100.0)) == 1.0


def test_duplicate_points_do_not_force_metres():
    """Kaksoiskappaleiden nollaetäisyys vetäisi mediaanin nollaan ja väittäisi
    jokaista pilveä metreiksi."""
    from ordinate.core.geometry.loader import metre_scale
    xyz = np.repeat(_floor_grid(250_000.0, 3000.0, 100.0), 3, axis=0)
    assert metre_scale(xyz) == 1.0

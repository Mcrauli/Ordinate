"""Monen skannin yhdistäminen ei saa vaatia koko projektia raakana muistiin."""
import numpy as np
import pytest

from ordinate.core.geometry import loader


def _write_ply(path, pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    o3d.io.write_point_cloud(str(path), pc)
    return path


def _slab(x0, n=40_000, seed=0):
    """Seinäpinta jonka pisteväli on selvästi alle yhdistelyvoxelin.

    Keilausdata on PINNOILLA, ei tilavuudessa hajallaan: 1 mm pisteväli
    pystypinnalla tarkoittaa että 10 mm voxeliin osuu kymmeniä pisteitä.
    Satunnainen pistepilvi kuutiossa ei harvenisi lainkaan eikä kertoisi
    yhdistelystä mitään.
    """
    rng = np.random.default_rng(seed)
    return np.column_stack([
        x0 + rng.normal(0.0, 3.0, n),            # pinta ±3 mm
        rng.uniform(0.0, 2000.0, n),
        rng.uniform(0.0, 2600.0, n),
    ])


def test_single_file_is_not_downsampled(tmp_path):
    """Yhden tiedoston polulla ei ole muistiongelmaa — tulos ei saa muuttua."""
    pts = _slab(0.0)
    p = _write_ply(tmp_path / "a.ply", pts)
    out = loader.load_and_merge([p])
    assert len(out.points) == len(pts)


def test_many_files_are_downsampled_before_merging(tmp_path):
    """Yhdistelmän on oltava selvästi raakaa pienempi.

    Mitattu koulun kellarilla: 37 asemaa on ~1 mrd pistettä eli ~24 GB raakana,
    kun työpilvi on lopulta 25 M pistettä. Harvennettuna huippu oli 5.0 GB.
    """
    paths = [_write_ply(tmp_path / f"s{i}.ply", _slab(i * 500.0, seed=i))
             for i in range(4)]
    raw = sum(len(_slab(i * 500.0, seed=i)) for i in range(4))
    out = loader.load_and_merge(paths)
    assert len(out.points) < raw * 0.9, "yhdistelmää ei harvennettu"


def test_merging_keeps_the_full_extent(tmp_path):
    """Harvennus ei saa kadottaa rakennuksen laajuutta — vain tiheyttä."""
    paths = [_write_ply(tmp_path / f"s{i}.ply", _slab(i * 5000.0, seed=i))
             for i in range(3)]
    out = np.asarray(loader.load_and_merge(paths).points)
    assert out[:, 0].min() < 100.0
    assert out[:, 0].max() > 9_900.0       # kolmas pinta on x = 10 000 mm

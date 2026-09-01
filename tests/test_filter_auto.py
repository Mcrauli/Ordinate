"""Auto-tila: iso tila saa semanttisen suodattimen myös matalana."""
import numpy as np
import pytest

from scan2bim.core.pipeline import (
    _FILTER_MIN_AREA_M2, _looks_like_retail, _occupancy_area_m2,
)


def _slab(size_m: float, height_mm: float, step: float = 250.0):
    """Vaakalaatta + katto: pohja-ala tunnettu, korkeus valittavissa."""
    o3d = pytest.importorskip("open3d")
    xs = np.arange(0.0, size_m * 1000.0, step)
    gx, gy = np.meshgrid(xs, xs)
    floor = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])
    ceil = floor + np.array([0.0, 0.0, height_mm])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack([floor, ceil]))
    return pc


def _auto_uses_pointnet(cloud) -> bool:
    return _looks_like_retail(cloud) or _occupancy_area_m2(cloud) >= _FILTER_MIN_AREA_M2


def test_a_large_low_space_gets_the_filter():
    """Koulun kellari: 7137 m², vapaa korkeus 1.78 m — jäi ennen suodattimetta."""
    cloud = _slab(90.0, 1800.0)          # 8100 m², matala
    assert not _looks_like_retail(cloud), "korkeusehto ei saa täyttyä"
    assert _auto_uses_pointnet(cloud)


def test_a_small_space_does_not():
    """Asunto ja talo regressoivat suodattimesta — ne jäävät alarajan alle."""
    cloud = _slab(9.0, 2600.0)           # 81 m²
    assert not _auto_uses_pointnet(cloud)


def test_a_tall_retail_space_still_gets_it():
    cloud = _slab(30.0, 6000.0)          # 900 m², korkea
    assert _looks_like_retail(cloud)
    assert _auto_uses_pointnet(cloud)

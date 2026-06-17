"""Kerrosjako-logiikan testit."""
import numpy as np
import pytest

from scan2bim.core.geometry.floor_splitter import detect_floors


def _make_floor_z(floor_z: float, height: float = 2800.0, n: int = 5000) -> np.ndarray:
    """Generoi Z-pisteitä yhdelle kerrokselle (lattia + seinät + katto)."""
    rng = np.random.default_rng(42)
    return rng.uniform(floor_z, floor_z + height, n).astype(np.float32)


def test_single_floor():
    z = _make_floor_z(0.0)
    floors = detect_floors(z)
    assert len(floors) == 1
    lo, hi = floors[0]
    assert lo <= 0.0
    assert hi >= 2800.0


def test_two_floors():
    z = np.concatenate([
        _make_floor_z(0.0, height=2800.0),
        _make_floor_z(3100.0, height=2800.0),  # 300mm laattaväli
    ])
    floors = detect_floors(z)
    assert len(floors) == 2
    assert floors[0][1] < floors[1][0] + 500  # ei päällekkäin (puskuri ok)


def test_three_floors():
    z = np.concatenate([
        _make_floor_z(0.0, height=3000.0),
        _make_floor_z(3300.0, height=3000.0),
        _make_floor_z(6600.0, height=3000.0),
    ])
    floors = detect_floors(z)
    assert len(floors) == 3


def test_very_short_z_returns_one_floor():
    z = np.linspace(0.0, 500.0, 100).astype(np.float32)
    floors = detect_floors(z)
    assert len(floors) == 1


def test_floor_bounds_cover_data():
    z = _make_floor_z(1000.0, height=2700.0)
    floors = detect_floors(z)
    lo, hi = floors[0]
    assert lo <= 1000.0
    assert hi >= 3700.0

"""Seinän kaistassa on oltava TASO, ei vain pintaa."""
import numpy as np
import pytest

from ordinate.core.semantics.flatness_prune import prune_flatless_walls
from ordinate.schemas.model import ElementSource, StructuralModel, Wall

_H = 2600.0


def _cloud(pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return pc


def _wall(wid="w0", y=0.0, length=8000.0, thickness=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[[0.0, y], [length, y]], height=_H, thickness=thickness,
                z_min=0.0)


def _plane(y, length=8000.0, step=25.0, jitter=0.0, seed=0):
    """Taso: pisteet millin sisällä samassa tasossa."""
    rng = np.random.RandomState(seed)
    xs = np.arange(0.0, length, step)
    zs = np.arange(700.0, 1900.0, step)
    gx, gz = np.meshgrid(xs, zs)
    ys = np.full(gx.size, y)
    if jitter:
        ys = ys + rng.uniform(-jitter, jitter, gx.size)
    return np.column_stack([gx.ravel(), ys, gz.ravel()])


def _model(*walls):
    m = StructuralModel()
    m.walls = list(walls)
    return m


def test_a_wall_on_a_plane_is_kept():
    m = _model(_wall())
    pts = np.vstack([_plane(-100.0, jitter=3.0), _plane(100.0, jitter=3.0, seed=1)])
    assert prune_flatless_walls(m, _cloud(pts), 0.0, _H) == []
    assert len(m.walls) == 1


def test_a_wall_on_scattered_clutter_is_removed():
    """Putkimetsä täyttää kaistan tasaisesti — hajonta on kymmeniä millejä."""
    m = _model(_wall())
    pts = np.vstack([_plane(-100.0, jitter=90.0), _plane(100.0, jitter=90.0, seed=2)])
    assert prune_flatless_walls(m, _cloud(pts), 0.0, _H) == ["w0"]
    assert m.walls == []


def test_a_noisy_but_real_surface_survives():
    """Synteettisen aineiston oma kohina on ~15 mm eikä se saa pudottaa seinää."""
    m = _model(_wall())
    pts = np.vstack([_plane(-100.0, jitter=18.0), _plane(100.0, jitter=18.0, seed=3)])
    assert prune_flatless_walls(m, _cloud(pts), 0.0, _H) == []


def test_a_short_wall_is_not_judged():
    m = _model(_wall(length=1500.0))
    pts = np.vstack([_plane(-100.0, length=1500.0, jitter=90.0)])
    assert prune_flatless_walls(m, _cloud(pts), 0.0, _H) == []
    assert len(m.walls) == 1


def test_a_wall_without_points_is_left_to_the_other_gates():
    m = _model(_wall())
    far = _plane(-100.0) + np.array([0.0, 50_000.0, 0.0])
    assert prune_flatless_walls(m, _cloud(far), 0.0, _H) == []
    assert len(m.walls) == 1

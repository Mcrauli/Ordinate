"""Seinä on piirrettävä suuntaan jossa pilvessä on pintaa."""
import numpy as np
import pytest

from scan2bim.core.semantics.direction_prune import prune_offdirection_walls
from scan2bim.schemas.model import ElementSource, StructuralModel, Wall

_H = 2600.0


def _cloud(pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return pc


def _wall(wid, a, b, thickness=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[list(a), list(b)], height=_H, thickness=thickness, z_min=0.0)


def _face(a, b, step=25.0):
    """Pystypinta janalta a→b, lattiasta kattoon."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    t = np.arange(0.0, L, step) / L
    xy = a + (b - a) * t[:, None]
    zs = np.arange(60.0, _H - 60.0, step)
    out = np.repeat(xy, len(zs), axis=0)
    return np.column_stack([out, np.tile(zs, len(xy))])


def _model(*walls):
    m = StructuralModel()
    m.walls = list(walls)
    return m


def _two_directions():
    """Pinnat 0° ja 90° suuntiin — kaksi tuettua suuntaa."""
    return np.vstack([
        _face((0.0, -100.0), (12000.0, -100.0)),
        _face((0.0, 100.0), (12000.0, 100.0)),
        _face((-100.0, 0.0), (-100.0, 12000.0)),
        _face((100.0, 0.0), (100.0, 12000.0)),
    ])


def test_a_wall_across_the_grain_is_removed():
    """45° vino seinä kun pilvessä on vain 0° ja 90° pintoja."""
    m = _model(_wall("vino", (2000.0, 2000.0), (9000.0, 9000.0)))
    assert prune_offdirection_walls(m, _cloud(_two_directions()), 0.0, _H) == ["vino"]
    assert m.walls == []


def test_walls_along_the_grain_are_kept():
    m = _model(_wall("a", (0.0, 0.0), (12000.0, 0.0)),
               _wall("b", (0.0, 0.0), (0.0, 12000.0)))
    assert prune_offdirection_walls(m, _cloud(_two_directions()), 0.0, _H) == []
    assert len(m.walls) == 2


def test_six_directions_are_all_kept():
    """Kellarissa on kuusi aitoa suuntaa 20° välein — sääntö ei saa olettaa
    Manhattan-maailmaa niin kuin kumottu `drop_skew` teki."""
    pts, walls = [], []
    for i, deg in enumerate((0.0, 20.0, 40.0, 90.0, 110.0, 130.0)):
        r = np.radians(deg)
        u = np.array([np.cos(r), np.sin(r)])
        n = np.array([-u[1], u[0]])
        c = np.array([3000.0 * i, 3000.0 * i])
        pts.append(_face(c - u * 5000.0 + n * 100.0, c + u * 5000.0 + n * 100.0))
        pts.append(_face(c - u * 5000.0 - n * 100.0, c + u * 5000.0 - n * 100.0))
        walls.append(_wall(f"w{i}", c - u * 5000.0, c + u * 5000.0))
    m = _model(*walls)
    assert prune_offdirection_walls(m, _cloud(np.vstack(pts)), 0.0, _H) == []
    assert len(m.walls) == 6


def test_a_short_wall_is_not_judged():
    m = _model(_wall("lyhyt", (2000.0, 2000.0), (3200.0, 3200.0)))
    assert prune_offdirection_walls(m, _cloud(_two_directions()), 0.0, _H) == []
    assert len(m.walls) == 1

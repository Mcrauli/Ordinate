"""Seinä joka ei erotu ympäristöstään ei ole seinä — paitsi jos mittari on sokea."""
import numpy as np
import pytest

from ordinate.core.semantics.contrast_prune import prune_uncontrasted_walls
from ordinate.schemas.model import ElementSource, StructuralModel, Wall

_H = 2600.0


def _cloud(pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return pc


def _wall(wid="w0", y=0.0, length=8000.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[[0.0, y], [length, y]], height=_H, thickness=200.0, z_min=0.0)


def _face(y, length=8000.0, step=30.0):
    """Pystypinta joka jatkuu lattiasta kattoon → seinämäinen."""
    xs = np.arange(0.0, length, step)
    zs = np.arange(60.0, _H - 60.0, step)
    gx, gz = np.meshgrid(xs, zs)
    return np.column_stack([gx.ravel(), np.full(gx.size, y), gz.ravel()])


def _clutter():
    """Pystypintaa yhtä tiheässä seinän pinnalla JA kontrollietäisyyksillä.

    Kontrolli on `_CTRL` verran seinän PINNASTA (paksuus/2 = 100 mm), joten
    vertailupinnat ovat 850 ja 1350 mm akselista.
    """
    ys = []
    for base in (0.0, 4000.0, 8000.0):
        ys += [base - 1350, base - 850, base - 100, base + 100,
               base + 850, base + 1350]
    return np.vstack([_face(y) for y in ys])


def _model(*walls):
    m = StructuralModel()
    m.walls = list(walls)
    return m


def _slabs(m):
    return m


def test_a_wall_with_more_surface_beside_it_is_removed():
    """Putkimetsä: pintaa on yhtä paljon joka puolella."""
    m = _model(_wall("w0"), _wall("w1", y=4000.0), _wall("w2", y=8000.0))
    pts = _clutter()
    dropped = prune_uncontrasted_walls(m, _cloud(pts), 0.0, _H)
    assert dropped == ["w0", "w1", "w2"]
    assert m.walls == []


def test_a_wall_that_stands_out_is_kept():
    """Aito seinä: pintaa on sen pinnalla eikä metrin sivussa."""
    m = _model(_wall("w0"), _wall("w1", y=4000.0), _wall("w2", y=8000.0))
    pts = np.vstack([_face(y) for y in (-100, 100, 3900, 4100, 7900, 8100)])
    assert prune_uncontrasted_walls(m, _cloud(pts), 0.0, _H) == []
    assert len(m.walls) == 3


def test_a_wall_in_a_blind_spot_is_not_judged():
    """Rohbaun 10 m halli: aidon seinän ympärillä ei ole yhtään pystypintaa.

    Silloin kontrasti on 1.00 pelkästä nollasta eikä se ole todiste mistään.
    """
    m = _model(_wall("w0"), _wall("w1", y=4000.0), _wall("w2", y=8000.0),
               _wall("kaukana", y=60000.0))
    pts = np.vstack([_face(y) for y in (-100, 100, 3900, 4100, 7900, 8100)])
    dropped = prune_uncontrasted_walls(m, _cloud(pts), 0.0, _H)
    assert "kaukana" not in dropped
    assert any(w.id == "kaukana" for w in m.walls)


def test_short_walls_are_not_judged():
    m = _model(_wall("lyhyt", length=1500.0), _wall("w1", y=4000.0),
               _wall("w2", y=8000.0))
    dropped = prune_uncontrasted_walls(m, _cloud(_clutter()), 0.0, _H)
    assert "lyhyt" not in dropped

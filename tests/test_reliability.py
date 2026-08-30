"""Luotettavuusraportti kertoo kun malli ei vastaa pilveä."""
import numpy as np
import pytest

from scan2bim.core.qa.reliability import measure
from scan2bim.schemas.model import ElementSource, StructuralModel, Wall

_H = 2600.0
_THICK_MARGIN = 60.0


def _cloud(pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return pc


def _wall(wid, y, thickness=200.0, length=8000.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[[0.0, y], [length, y]], height=_H, thickness=thickness,
                z_min=0.0)


def _face(y, length=8000.0, step=30.0):
    xs = np.arange(0.0, length, step)
    zs = np.arange(60.0, _H - 60.0, step)
    gx, gz = np.meshgrid(xs, zs)
    return np.column_stack([gx.ravel(), np.full(gx.size, y), gz.ravel()])


def _model(*walls):
    m = StructuralModel()
    m.walls = list(walls)
    return m


def test_a_good_model_raises_no_warning():
    m = _model(_wall("w0", 0.0), _wall("w1", 6000.0), _wall("w2", 12000.0))
    pts = np.vstack([_face(y) for y in (-100, 100, 5900, 6100, 11900, 12100)])
    rep = measure(m, _cloud(pts), 0.0, _H)
    assert rep.judged == 3
    assert rep.contrast_median > 1.5
    assert rep.hit_frac == 1.0
    assert rep.warnings == []


def test_walls_that_do_not_stand_out_are_reported():
    """Kellari: pintaa on yhtä paljon seinällä ja sen vierellä."""
    m = _model(_wall("w0", 0.0), _wall("w1", 6000.0), _wall("w2", 12000.0))
    ys = []
    for base in (0.0, 6000.0, 12000.0):
        ys += [base - 1350, base - 850, base - 100, base + 100,
               base + 850, base + 1350]
    rep = measure(m, _cloud(np.vstack([_face(y) for y in ys])), 0.0, _H)
    assert rep.contrast_median <= 1.2
    assert any("erotu" in w for w in rep.warnings)


def test_a_wrong_thickness_is_reported():
    """Malli sanoo 300 mm, pinnat ovat 180 mm päässä toisistaan.

    Seinät ovat oikeassa paikassa (pinta osuu kaistaan), joten VAIN
    paksuusvaroituksen saa laueta — muuten testi menisi läpi väärästä syystä.
    """
    m = _model(_wall("w0", 0.0, thickness=300.0),
               _wall("w1", 6000.0, thickness=300.0),
               _wall("w2", 12000.0, thickness=300.0))
    pts = np.vstack([_face(y) for y in (-90, 90, 5910, 6090, 11910, 12090)])
    rep = measure(m, _cloud(pts), 0.0, _H)
    assert rep.hit_frac == 1.0, "sijaintivaroitus ei saa sekaantua tähän"
    assert rep.thickness_bias is not None and rep.thickness_bias > _THICK_MARGIN
    assert any("poikkeaa pinnoista mitatusta" in w for w in rep.warnings)


def test_walls_in_empty_space_are_reported():
    m = _model(_wall("w0", 0.0), _wall("w1", 6000.0), _wall("w2", 12000.0))
    pts = np.vstack([_face(y) for y in (-100, 100)])
    rep = measure(m, _cloud(pts), 0.0, _H)
    assert rep.hit_frac is not None and rep.hit_frac < 0.5
    assert any("pintansa" in w for w in rep.warnings)


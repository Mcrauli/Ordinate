"""Indeksointi ei saa muuttaa tulosta — vain nopeutta.

Kaksi nopeusmuutosta lepää tämän varassa: pilvikohtainen indeksivälimuisti
(22 rakennusta → 4) ja kiertopassien kaistahaku (`fine_rotate_walls`,
`refine_skew_walls`). Molempien on tuotettava BITILLEEN sama akseli kuin koko
pistetaulukon skannaus, muuten kyseessä ei ole nopeutus vaan muutos.
"""
import numpy as np
import pytest

from scan2bim.core.geometry.xy_index import XYIndex, clear_index_cache, index_for
from scan2bim.core.semantics.orthogonal import fine_rotate_walls, refine_skew_walls
from scan2bim.schemas.model import ElementSource, Wall

_H = 2700.0


def _wall(wid, a, b, thickness=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[list(a), list(b)], height=_H, thickness=thickness, z_min=0.0)


def _face(a, b, step=12.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    t = np.arange(0.0, L, step) / L
    xy = a + (b - a) * t[:, None]
    zs = np.arange(300.0, _H - 300.0, step)
    out = np.repeat(xy, len(zs), axis=0)
    return np.column_stack([out, np.tile(zs, len(xy))])


def _scene():
    """Pilvi jossa on suora seinä, hieman vinossa oleva ja aidosti vino."""
    rng = np.random.default_rng(7)
    parts = []
    for a, b in (((0.0, 0.0), (14000.0, 0.0)),
                 ((0.0, 200.0), (14000.0, 200.0)),
                 ((0.0, 6000.0), (13000.0, 6400.0)),
                 ((0.0, 6200.0), (13000.0, 6600.0)),
                 ((2000.0, 12000.0), (12000.0, 13200.0)),
                 ((2000.0, 12200.0), (12000.0, 13400.0))):
        parts.append(_face(a, b))
    pts = np.vstack(parts)
    pts += rng.normal(0.0, 2.0, pts.shape)
    return pts


def _axes(walls):
    return [tuple(map(tuple, w.axis)) for w in walls]


@pytest.fixture(scope="module")
def scene():
    pts = _scene()
    assert len(pts) > 300_000, len(pts)
    return pts


def _walls():
    return [_wall("suora", (0.0, 100.0), (14000.0, 100.0)),
            _wall("kalteva", (0.0, 6100.0), (13000.0, 6500.0)),
            _wall("vino", (2000.0, 12100.0), (12000.0, 12100.0))]


def test_fine_rotate_is_bit_identical_with_an_index(scene):
    idx = XYIndex(scene)
    a = fine_rotate_walls(_walls(), scene, z_min=500.0, z_max=2400.0)
    b = fine_rotate_walls(_walls(), scene, z_min=500.0, z_max=2400.0, index=idx)
    assert _axes(a) == _axes(b)


def test_refine_skew_is_bit_identical_with_an_index(scene):
    idx = XYIndex(scene)
    a = refine_skew_walls(_walls(), scene, z_min=500.0, z_max=2400.0)
    b = refine_skew_walls(_walls(), scene, z_min=500.0, z_max=2400.0, index=idx)
    assert _axes(a) == _axes(b)


def test_the_rotation_actually_moves_something(scene):
    """Mutaatiosuoja: jos kierto ei tee mitään, identtisyys olisi tyhjä väite."""
    before = _walls()
    after = fine_rotate_walls(before, scene, z_min=500.0, z_max=2400.0)
    assert _axes(before) != _axes(after)


class _FakeCloud:
    def __init__(self, pts):
        self.points = pts


def test_the_same_cloud_is_indexed_once(scene):
    clear_index_cache()
    c = _FakeCloud(scene)
    first = index_for(c, scene)
    assert index_for(c, scene) is first
    assert index_for(_FakeCloud(scene), scene) is not first
    clear_index_cache()
    assert index_for(c, scene) is not first


def test_a_resized_cloud_is_reindexed(scene):
    """Paikallaan muokattu pilvi ei saa saada vanhaa indeksiä."""
    clear_index_cache()
    c = _FakeCloud(scene)
    first = index_for(c, scene)
    assert index_for(c, scene[:-10]) is not first
    clear_index_cache()

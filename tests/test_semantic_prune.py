"""Seinä jonka pinta on putkea tai kanavaa ei ole seinä."""
import numpy as np
import pytest

from ordinate.core.semantics.semantic_prune import prune_non_wall_surfaces
from ordinate.schemas.model import ElementSource, StructuralModel, Wall

_WALL, _CLUTTER = 2, 12


class _Labels:
    """Kiinteä luokka koko pilvelle — testin ei tarvitse ajaa PointNettiä."""

    def __init__(self, cls):
        self._cls = cls

    def lookup(self, pts):
        return np.full(len(pts), self._cls, dtype=np.int8)


def _cloud(pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return pc


def _wall(wid="w0", length=6000.0):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="normals"),
        axis=[[0.0, 0.0], [length, 0.0]], height=2600.0,
        thickness=200.0, z_min=0.0,
    )


def _surface(length=6000.0, offset=100.0, n_z=40):
    """Pisteitä seinän molemmilla pinnoilla koko korkeudelta."""
    xs = np.arange(0.0, length, 40.0)
    zs = np.linspace(50.0, 2550.0, n_z)
    gx, gz = np.meshgrid(xs, zs)
    out = []
    for side in (-offset, offset):
        out.append(np.column_stack([gx.ravel(), np.full(gx.size, side), gz.ravel()]))
    return np.vstack(out)


def _model(*walls):
    m = StructuralModel()
    m.walls = list(walls)
    return m


def test_a_wall_on_clutter_is_removed():
    """Kellarissa 124 seinää 400:sta oli putkien ja kanavien päällä."""
    m = _model(_wall())
    dropped = prune_non_wall_surfaces(m, _cloud(_surface()), _Labels(_CLUTTER))
    assert dropped == ["w0"]
    assert m.walls == []


def test_a_wall_on_wall_surface_is_kept():
    m = _model(_wall())
    dropped = prune_non_wall_surfaces(m, _cloud(_surface()), _Labels(_WALL))
    assert dropped == []
    assert len(m.walls) == 1


def test_nothing_happens_without_labels():
    """Sääntö ei voi toimia ilman suodatinta — silloin se on no-op."""
    m = _model(_wall())
    assert prune_non_wall_surfaces(m, _cloud(_surface()), None) == []
    assert len(m.walls) == 1


def test_a_wall_without_points_is_left_to_geometric_pruning():
    """Ei näyttöä ei ole todiste: `prune_unsupported_walls` hoitaa tyhjät."""
    m = _model(_wall())
    far = _surface() + np.array([0.0, 50_000.0, 0.0])
    assert prune_non_wall_surfaces(m, _cloud(far), _Labels(_CLUTTER)) == []
    assert len(m.walls) == 1


def test_a_short_wall_is_not_judged():
    """Lyhyt seinä ei kerää tarpeeksi näyttöä — sitä ei saa tuomita."""
    m = _model(_wall(length=1200.0))
    pts = _surface(length=1200.0)
    assert prune_non_wall_surfaces(m, _cloud(pts), _Labels(_CLUTTER)) == []
    assert len(m.walls) == 1


class _Frac:
    """Seinäluokka osuudelle seinän pituudesta, loput clutteria."""

    def __init__(self, frac):
        self._frac = frac

    def lookup(self, pts):
        out = np.full(len(pts), _CLUTTER, dtype=np.int8)
        out[np.asarray(pts)[:, 0] < self._frac * 6000.0] = _WALL
        return out


def test_a_wall_that_is_mostly_clutter_is_removed():
    """Enemmistöääni: 40 % seinää ei riitä.

    Kellarin valeseinät seisovat putkilla ja kanavilla, joiden seassa on
    seinäpistettä sen verran että vanha 0.30 päästi ne läpi.
    """
    m = _model(_wall())
    assert prune_non_wall_surfaces(m, _cloud(_surface()), _Frac(0.40)) == ["w0"]
    assert m.walls == []


def test_a_wall_that_is_mostly_wall_is_kept():
    """Sama kaista toisin päin: 60 % seinää jää."""
    m = _model(_wall())
    assert prune_non_wall_surfaces(m, _cloud(_surface()), _Frac(0.60)) == []
    assert len(m.walls) == 1

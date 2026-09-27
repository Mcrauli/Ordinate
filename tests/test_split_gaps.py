"""Seinä pilkotaan kohdasta jossa pintaa ei ole — mutta ei oviaukosta."""
import numpy as np

from ordinate.core.semantics.split_gaps import split_walls_at_gaps
from ordinate.schemas.model import ElementSource, Wall


def _wall(x0, x1, thickness=200.0, wid="w0"):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="normals"),
        axis=[[x0, 0.0], [x1, 0.0]], height=2600.0,
        thickness=thickness, z_min=0.0,
    )


def _surface(x_from, x_to, thickness=200.0, step=25.0, n_z=60):
    """Seinäpinnan pisteet molemmilla puolilla akselia."""
    xs = np.arange(x_from, x_to, step)
    zs = np.linspace(100.0, 2500.0, n_z)
    gx, gz = np.meshgrid(xs, zs)
    half = thickness / 2.0
    out = []
    for side in (-half, half):
        out.append(np.column_stack([gx.ravel(), np.full(gx.size, side), gz.ravel()]))
    return np.vstack(out)


def test_wall_with_full_surface_is_not_split():
    pts = _surface(0.0, 10_000.0)
    out = split_walls_at_gaps([_wall(0.0, 10_000.0)], pts)
    assert len(out) == 1


def test_a_door_sized_gap_does_not_split_the_wall():
    """Oviaukko on laillinen kattamaton väli — seinän kuuluu jatkua sen yli."""
    pts = np.vstack([_surface(0.0, 4000.0), _surface(5000.0, 10_000.0)])
    out = split_walls_at_gaps([_wall(0.0, 10_000.0)], pts)
    assert len(out) == 1, "metrin aukko ei saa katkaista seinää"


def test_a_gap_of_metres_splits_the_wall():
    """Mitattu koulun kellarilla: seinät jatkuivat metrien matkan tyhjän yli."""
    pts = np.vstack([_surface(0.0, 4000.0), _surface(11_000.0, 15_000.0)])
    out = split_walls_at_gaps([_wall(0.0, 15_000.0)], pts)
    assert len(out) == 2
    lens = sorted(float(np.linalg.norm(np.array(w.axis[1]) - np.array(w.axis[0])))
                  for w in out)
    assert all(L >= 900.0 for L in lens)
    assert sum(lens) < 15_000.0, "pilkkomisen on lyhennettävä yhteispituutta"


def test_a_wall_with_no_surface_at_all_is_left_alone():
    """Ilman evidenssiä ei voi päätellä mihin katkaista — jätä karsinnalle."""
    pts = _surface(50_000.0, 60_000.0)
    out = split_walls_at_gaps([_wall(0.0, 10_000.0)], pts)
    assert len(out) == 1


def test_pieces_keep_thickness_and_height():
    pts = np.vstack([_surface(0.0, 3000.0, thickness=120.0),
                     _surface(9000.0, 12_000.0, thickness=120.0)])
    out = split_walls_at_gaps([_wall(0.0, 12_000.0, thickness=120.0)], pts)
    assert len(out) == 2
    for w in out:
        assert w.thickness == 120.0
        assert w.height == 2600.0

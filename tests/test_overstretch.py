"""Ylivenytys: seina piirretty evidenssin yli.

`snap_corners`/`close_open_corners` venyttavat paita vain GEOMETRISELLA rajalla,
eivat kysy onko venytetylla osalla pisteita. Mitattu asuntoskannauksella
(`data/_extent_qa.py`): wall_005 kate 0.63, hannat 600 + 800 mm.

Leikkaus koskee VAIN paata joka on kattamaton JA yha irrallaan. Nurkkaan osuvaa
paata ei kosketa, koska silloin venytys on laillinen mallinnusvara.
"""
import numpy as np
import open3d as o3d

from scan2bim.core.semantics.overstretch import trim_overstretched_walls
from scan2bim.schemas.model import (
    ElementSource, Opening, Slab, StructuralModel, Wall,
)

_H = 2700.0
_T = 100.0


def _wall(wid, x0, y0, x1, y1, thickness=_T):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y0], [x1, y1]], height=_H, thickness=thickness, z_min=0.0,
    )


def _slabs():
    ring = [[-20000.0, -20000.0], [20000.0, -20000.0], [20000.0, 20000.0], [-20000.0, 20000.0]]
    return [
        Slab(id="s0", confidence=1.0, classification="slab", source=ElementSource(method="manual"),
             slab_type="floor", boundary=ring, elevation=0.0, thickness=200.0),
        Slab(id="s1", confidence=1.0, classification="slab", source=ElementSource(method="manual"),
             slab_type="ceiling", boundary=ring, elevation=_H, thickness=200.0),
    ]


def _model(walls, openings=()):
    return StructuralModel(walls=list(walls), slabs=_slabs(), openings=list(openings))


def _face(x_from, x_to, y, step=40.0, z_lo=500.0, z_hi=_H - 400.0):
    """Pystypinta y-tasolla valilla [x_from, x_to]."""
    x = np.arange(x_from, x_to, step)
    z = np.arange(z_lo, z_hi, step)
    xx, zz = np.meshgrid(x, z)
    return np.column_stack([xx.ravel(), np.full(xx.size, y), zz.ravel()])


def _face_y(y_from, y_to, x, step=40.0, z_lo=500.0, z_hi=_H - 400.0):
    """Pystypinta x-tasolla valilla [y_from, y_to]."""
    y = np.arange(y_from, y_to, step)
    z = np.arange(z_lo, z_hi, step)
    yy, zz = np.meshgrid(y, z)
    return np.column_stack([np.full(yy.size, x), yy.ravel(), zz.ravel()])


def _both_faces(x_from, x_to, thickness=_T):
    return np.vstack([_face(x_from, x_to, -thickness / 2.0),
                      _face(x_from, x_to, thickness / 2.0)])


def _cloud(*parts):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pcd


def test_uncovered_loose_tail_is_trimmed():
    """Pinta 0-3000, akseli 0-4000 -> irrallinen 1000 mm hanta pois."""
    m = _model([_wall("w0", 0, 0, 4000, 0)])
    got = trim_overstretched_walls(m, _cloud(_both_faces(0.0, 3000.0)))
    assert [w for w, _ in got] == ["w0"], got
    assert abs(m.walls[0].axis[1][0] - 3000.0) <= _BIN_TOL, m.walls[0].axis
    assert abs(m.walls[0].axis[0][0]) <= _BIN_TOL


_BIN_TOL = 200.0


def test_fully_covered_wall_is_left_alone():
    m = _model([_wall("w0", 0, 0, 4000, 0)])
    assert trim_overstretched_walls(m, _cloud(_both_faces(0.0, 4000.0))) == []
    assert m.walls[0].axis == [[0.0, 0.0], [4000.0, 0.0]]


def test_tail_that_closes_a_corner_is_kept():
    """Sama kattamaton hanta, mutta pea osuu toiseen seinaan -> ei kosketa.

    Tama on se ehto joka tekee leikkauksesta turvallisen: venytys nurkkaan on
    laillinen mallinnusvara, roikkuva hanta ei.
    """
    corner = _wall("w1", 4000, 0, 4000, 4000)
    m = _model([_wall("w0", 0, 0, 4000, 0), corner])
    cloud = _cloud(_both_faces(0.0, 3000.0), _face_y(0.0, 4000.0, 4000.0 - _T / 2.0))
    assert trim_overstretched_walls(m, cloud) == []
    assert m.walls[0].axis[1][0] == 4000.0


def test_short_tail_is_modelling_slack_not_an_error():
    """400 mm kattamaton hanta jaa: alle _MIN_TAIL."""
    m = _model([_wall("w0", 0, 0, 4000, 0)])
    assert trim_overstretched_walls(m, _cloud(_both_faces(0.0, 3600.0))) == []


def test_uncovered_middle_is_a_doorway_not_an_overstretch():
    """Aukko keskella ei ole venytys -> seinaa ei leikata."""
    m = _model([_wall("w0", 0, 0, 5000, 0)])
    cloud = _cloud(_both_faces(0.0, 1800.0), _both_faces(3200.0, 5000.0))
    assert trim_overstretched_walls(m, cloud) == []
    assert m.walls[0].axis == [[0.0, 0.0], [5000.0, 0.0]]


def test_both_ends_loose_and_uncovered_are_both_trimmed():
    m = _model([_wall("w0", -1000, 0, 5000, 0)])
    got = trim_overstretched_walls(m, _cloud(_both_faces(0.0, 4000.0)))
    assert len(got) == 1
    ax = m.walls[0].axis
    assert abs(ax[0][0] - 0.0) <= _BIN_TOL and abs(ax[1][0] - 4000.0) <= _BIN_TOL, ax


def test_trim_never_leaves_a_stub():
    """Jos leikkaus jattaisi alle _MIN_KEEP:n seinan, ei leikata lainkaan."""
    m = _model([_wall("w0", 0, 0, 4000, 0)])
    got = trim_overstretched_walls(m, _cloud(_both_faces(1500.0, 2000.0)))
    assert got == []
    assert m.walls[0].axis == [[0.0, 0.0], [4000.0, 0.0]]


def test_wall_with_no_surface_at_all_is_left_to_pruning():
    """Tama ei ole venytysongelma — `prune_unsupported_walls` omistaa sen."""
    m = _model([_wall("w0", 0, 0, 4000, 0)])
    assert trim_overstretched_walls(m, _cloud(_face(0.0, 4000.0, 3000.0))) == []


def test_opening_in_the_trimmed_tail_is_dropped():
    """IFC:hen ei saa jaada aukkoa seinan ulkopuolelle."""
    op = Opening(
        id="op0", confidence=1.0, classification="opening",
        source=ElementSource(method="manual"), opening_type="door", wall_id="w0",
        position_along=3600.0, width=900.0, sill_height=0.0, opening_height=2100.0,
    )
    m = _model([_wall("w0", 0, 0, 4000, 0)], [op])
    assert trim_overstretched_walls(m, _cloud(_both_faces(0.0, 3000.0)))
    assert m.openings == []


def test_opening_shifts_when_the_start_end_is_trimmed():
    """position_along mitataan p0:sta, joten p0:n siirto siirtaa aukkoa."""
    op = Opening(
        id="op0", confidence=1.0, classification="opening",
        source=ElementSource(method="manual"), opening_type="door", wall_id="w0",
        position_along=2000.0, width=900.0, sill_height=0.0, opening_height=2100.0,
    )
    m = _model([_wall("w0", -1000, 0, 4000, 0)], [op])
    assert trim_overstretched_walls(m, _cloud(_both_faces(0.0, 4000.0)))
    assert abs(m.openings[0].position_along - 1000.0) <= _BIN_TOL


def test_sparse_scan_still_trims():
    """Kate on suhteellinen kysymys 'onko taalla mitaan', ei tiheysraja."""
    m = _model([_wall("w0", 0, 0, 4000, 0)])
    cloud = _cloud(_both_faces(0.0, 3000.0, _T)[::120])
    got = trim_overstretched_walls(m, cloud)
    assert [w for w, _ in got] == ["w0"], got


def test_diagonal_wall_is_trimmed_along_its_own_axis():
    """Leikkaus tapahtuu akselin suunnassa, ei maailman akseleilla."""
    L = 5000.0
    u = np.array([np.cos(np.radians(37.0)), np.sin(np.radians(37.0))])
    a = np.array([1000.0, -2000.0])
    b = a + u * L
    n = np.array([-u[1], u[0]])
    s = np.arange(0.0, 3400.0, 40.0)
    z = np.arange(500.0, _H - 400.0, 40.0)
    ss, zz = np.meshgrid(s, z)
    pts = []
    for off in (-_T / 2.0, _T / 2.0):
        p = a + np.outer(ss.ravel(), u) + n * off
        pts.append(np.column_stack([p, zz.ravel()]))
    m = _model([_wall("w0", a[0], a[1], b[0], b[1])])
    got = trim_overstretched_walls(m, _cloud(*pts))
    assert len(got) == 1
    end = np.asarray(m.walls[0].axis[1])
    assert abs(float((end - a) @ u) - 3400.0) <= _BIN_TOL, end

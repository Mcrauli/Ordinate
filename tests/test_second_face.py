"""Kontuurin katve: puolen metrin paassa seisova toinen seina.

`cv2.findContours` jaljittaa vapaan tilan reunan, joten se nakee vain
ENSIMMAISEN pinnan. Rohbau3D-GT:lla mitattuna se on suurin yksittainen
kattavuusvaje: 20.6 %:n vajeesta 52.6 % istuu 400-700 mm paassa mallipinnasta
ja on GT:ssa omia Drywall-instanssejaan.
"""
import numpy as np
import open3d as o3d

from scan2bim.core.semantics.second_face import find_hidden_walls
from scan2bim.schemas.model import ElementSource, Wall

_H = 3000.0
_T = 200.0


def _wall(wid, x0, y0, x1, y1, thickness=_T):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y0], [x1, y1]], height=_H, thickness=thickness, z_min=0.0,
    )


def _surface(y, x_from=0.0, x_to=30000.0, step=50.0, z_lo=100.0, z_hi=_H - 100.0):
    x = np.arange(x_from, x_to, step)
    z = np.arange(z_lo, z_hi, step)
    xx, zz = np.meshgrid(x, z)
    return np.column_stack([xx.ravel(), np.full(xx.size, y), zz.ravel()])


def _cloud(*parts):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pcd


def test_wall_hidden_behind_another_is_found():
    """Betoniperimetri + 500 mm sisapuolella kipsiseina -> kaksi seinaa, ei yksi."""
    w = _wall("w0", 0, 0, 30000, 0)
    cloud = _cloud(_surface(-_T / 2), _surface(_T / 2), _surface(600.0))
    found = find_hidden_walls([w], cloud)
    assert len(found) == 1, [f.axis for f in found]
    got = found[0]
    assert got.source.method == "second_face"
    # Nakyva pinta on emaseinaan pain -> runko jaa sen taakse.
    assert abs(got.axis[0][1] - (600.0 + got.thickness / 2.0)) < 60.0, got.axis
    assert abs(got.axis[0][0]) < 1.0 and abs(got.axis[1][0] - 30000.0) < 1.0


def test_plain_wall_does_not_grow_a_twin():
    """Pelkka seina ilman mitaan takanaan ei saa synnyttaa toista."""
    w = _wall("w0", 0, 0, 30000, 0)
    assert find_hidden_walls([w], _cloud(_surface(-_T / 2), _surface(_T / 2))) == []


def test_scattered_clutter_behind_a_wall_is_not_a_wall():
    """Hajanainen roina 600 mm paassa: massaa on, mutta ei yhtenaista pintaa."""
    rng = np.random.default_rng(0)
    n = 40_000
    blob = np.column_stack([
        rng.uniform(0.0, 3000.0, n),                 # vain seinan alkupaassa
        rng.normal(600.0, 15.0, n),
        rng.uniform(200.0, _H - 200.0, n),
    ])
    w = _wall("w0", 0, 0, 30000, 0)
    found = find_hidden_walls([w], _cloud(_surface(-_T / 2), _surface(_T / 2), blob))
    assert found == [], [f.axis for f in found]


def test_short_wall_never_claims_a_hidden_one():
    """Lyhyt seina ei voi todistaa jatkuvuutta -> ei saa keksia seinia."""
    w = _wall("w0", 0, 0, 3000, 0)
    cloud = _cloud(_surface(-_T / 2, x_to=3000.0), _surface(_T / 2, x_to=3000.0),
                   _surface(600.0, x_to=3000.0))
    assert find_hidden_walls([w], cloud) == []


def test_own_far_face_is_not_mistaken_for_a_hidden_wall():
    """Paksun seinan oma vastapinta ei ole eri seina."""
    w = _wall("w0", 0, 0, 30000, 0, thickness=600.0)
    cloud = _cloud(_surface(-300.0), _surface(300.0))
    assert find_hidden_walls([w], cloud) == []


def _boards(y0, y1, levels, x_to=30000.0, step=50.0):
    """Vaakatasot valiin y0..y1 — hyllylaudat."""
    x = np.arange(0.0, x_to, step)
    y = np.arange(y0, y1, step)
    xx, yy = np.meshgrid(x, y)
    out = []
    for z in levels:
        out.append(np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)]))
    return np.vstack(out)


def test_shelf_front_is_not_a_wall_because_the_shelf_has_shelves():
    """Lattia-katto-hyllyn etupinta: sama kuvio kuin seina, mutta valissa tasot."""
    w = _wall("w0", 0, 0, 30000, 0)
    cloud = _cloud(_surface(-_T / 2), _surface(_T / 2), _surface(900.0),
                   _boards(150.0, 850.0, [500.0, 1400.0, 2300.0]))
    assert find_hidden_walls([w], cloud) == []


def test_a_single_beam_in_the_gap_does_not_veto_a_real_wall():
    """Yksi vaakataso valissa on palkki tai kanava, ei hyllykko."""
    w = _wall("w0", 0, 0, 30000, 0)
    cloud = _cloud(_surface(-_T / 2), _surface(_T / 2), _surface(900.0),
                   _boards(150.0, 850.0, [2300.0]))
    assert len(find_hidden_walls([w], cloud)) == 1


def test_a_row_of_furniture_is_not_one_wall():
    """Sohva + kaappi + komero perakkain: yhta pitka pinta, reunat heittelevat."""
    w = _wall("w0", 0, 0, 30000, 0)
    sofa = _surface(600.0, x_from=0.0, x_to=12000.0, z_lo=100.0, z_hi=800.0)
    cab = _surface(600.0, x_from=12000.0, x_to=20000.0, z_lo=100.0, z_hi=1800.0)
    closet = _surface(600.0, x_from=20000.0, x_to=30000.0, z_lo=100.0, z_hi=_H - 100.0)
    cloud = _cloud(_surface(-_T / 2), _surface(_T / 2), sofa, cab, closet)
    assert find_hidden_walls([w], cloud) == [], "huonekaluketju ei ole seina"


def test_measured_height_comes_from_the_surface_not_the_parent():
    """3 m valiseina 10 m hallissa: korkeus mitataan pinnasta, ei emaseinasta."""
    w = _wall("w0", 0, 0, 30000, 0)
    w.height = 10000.0
    cloud = _cloud(_surface(-_T / 2, z_hi=9900.0), _surface(_T / 2, z_hi=9900.0),
                   _surface(600.0, z_lo=400.0, z_hi=3400.0))
    found = find_hidden_walls([w], cloud)
    assert len(found) == 1
    assert abs(found[0].height - 3000.0) < 300.0, found[0].height
    assert abs(found[0].z_min - 400.0) < 300.0, found[0].z_min


def test_a_duct_line_floating_in_a_tall_hall_is_not_a_wall():
    """1.1 m kaista 10 m hallissa: yhtenainen pinta, mutta ei seina."""
    w = _wall("w0", 0, 0, 30000, 0)
    w.height = 10000.0
    cloud = _cloud(_surface(-_T / 2, z_hi=9900.0), _surface(_T / 2, z_hi=9900.0),
                   _surface(600.0, z_lo=5600.0, z_hi=6700.0))
    assert find_hidden_walls([w], cloud) == []


def test_sparse_scan_still_finds_the_hidden_wall():
    """Massavaatimus on suhteessa emaseinan omaan pintaan, ei pistemaaraan."""
    w = _wall("w0", 0, 0, 30000, 0)
    cloud = _cloud(_surface(-_T / 2, step=400.0), _surface(_T / 2, step=400.0),
                   _surface(600.0, step=400.0))
    assert len(find_hidden_walls([w], cloud)) == 1

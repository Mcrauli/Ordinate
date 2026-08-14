"""Kuvaohjattu aukkodetektio: lapinakyvyys on GEOMETRINEN totuus.

Skannerin sade nakee seinatason OHI = aito aukko; maalatulla umpiseinalla on
pisteet seinatasolla. Asemat tulevat E57:n kuvaposeista, joten synteettinen
asema syotetaan _load_stations:n tilalle — itse paatos tehdaan pistepilven
syvyyspuskurista, eivatka kuvien pikselit vaikuta siihen mitenkaan.
"""
import numpy as np
import pytest

pytest.importorskip("cv2")

from scan2bim.core.segmentation import image_openings as io  # noqa: E402
from scan2bim.schemas.model import ElementSource, Wall  # noqa: E402

_L = 6000.0        # seinan pituus mm
_H = 2700.0        # seinan korkeus mm
_STATION = np.array([3000.0, -3000.0, 1500.0])
_BACK_Y = 6000.0   # takaseina: aukon lapi nakyva pinta


def _wall():
    return Wall(
        id="wall_000", confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[0.0, 0.0], [_L, 0.0]], height=_H, thickness=200.0, z_min=0.0,
    )


def _grid(x0, x1, z0, z1, y, step=25.0):
    xs = np.arange(x0, x1, step)
    zs = np.arange(z0, z1, step)
    X, Z = np.meshgrid(xs, zs)
    return np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()])


def _wall_points(hole=None):
    """Seinapinta y=0; hole=(x0,x1,z0,z1) jattaa aukon kohdan tyhjaksi."""
    pts = _grid(0.0, _L, 0.0, _H, 0.0)
    if hole is not None:
        x0, x1, z0, z1 = hole
        keep = ~((pts[:, 0] >= x0) & (pts[:, 0] <= x1)
                 & (pts[:, 2] >= z0) & (pts[:, 2] <= z1))
        pts = pts[keep]
    back = _grid(-2000.0, _L + 2000.0, 0.0, _H, _BACK_Y)
    return np.vstack([pts, back])


def _fake_stations(_e57_path):
    """Yksi asema. Kuvien SISALTO ei vaikuta tulokseen — vain sijainti."""
    return [_STATION]


@pytest.fixture(autouse=True)
def _stub_stations(monkeypatch):
    monkeypatch.setattr(io, "_load_stations", _fake_stations)


def _detect(pts):
    return io.detect_image_openings([_wall()], "dummy.e57", pts)


def test_see_through_hole_is_found_as_window():
    hole = (2200.0, 3800.0, 900.0, 2100.0)
    ops = _detect(_wall_points(hole))
    assert len(ops) == 1, [f"{o.width:.0f}x{o.opening_height:.0f}" for o in ops]
    o = ops[0]
    assert o.opening_type == "window", f"sill {o.sill_height:.0f}"
    assert o.wall_id == "wall_000"
    assert o.source.notes == "image-seethru"
    # 1600 x 1200 mm aukko, 20 mm/px -> muutaman pikselin tarkkuus riittaa
    assert o.width == pytest.approx(1600.0, abs=300.0), o.width
    assert o.opening_height == pytest.approx(1200.0, abs=300.0), o.opening_height
    assert o.position_along == pytest.approx(2200.0, abs=300.0), o.position_along


def test_painted_solid_wall_gives_no_opening():
    """Umpiseinalla on pisteet seinatasolla -> ei lapinakyvyytta -> ei aukkoa."""
    assert _detect(_wall_points(None)) == []


def test_floor_level_hole_is_a_door():
    ops = _detect(_wall_points((2200.0, 3400.0, 0.0, 2100.0)))
    assert len(ops) == 1
    assert ops[0].opening_type == "door", f"sill {ops[0].sill_height:.0f}"


def test_occluding_object_suppresses_the_wall():
    """Kaluste seinan edessa -> okkluusio yli 60 % -> seina ohitetaan kokonaan."""
    pts = _wall_points((2200.0, 3800.0, 900.0, 2100.0))
    screen = _grid(-1000.0, _L + 1000.0, 0.0, _H, -1500.0, step=25.0)
    assert _detect(np.vstack([pts, screen])) == []


def test_no_stations_is_a_no_op(monkeypatch):
    monkeypatch.setattr(io, "_load_stations", lambda _p: [])
    assert _detect(_wall_points((2200.0, 3800.0, 900.0, 2100.0))) == []


def test_short_wall_is_skipped():
    short = Wall(
        id="w_short", confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[0.0, 0.0], [700.0, 0.0]], height=_H, thickness=200.0, z_min=0.0,
    )
    pts = _wall_points((200.0, 500.0, 900.0, 2100.0))
    assert io.detect_image_openings([short], "dummy.e57", pts) == []


def test_station_behind_the_wall_is_not_used():
    """Vino/takana oleva asema ei kelpaa (cosang < 0.6) -> ei aukkoja."""
    # lahes seinan tasossa: v on melkein kohtisuorassa normaalia vastaan
    def _side(_p):
        return [np.array([-9000.0, -200.0, 1500.0])]
    io._load_stations = _side
    try:
        assert _detect(_wall_points((2200.0, 3800.0, 900.0, 2100.0))) == []
    finally:
        io._load_stations = _fake_stations

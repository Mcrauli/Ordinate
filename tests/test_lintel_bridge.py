"""bridge_lintel_gaps: ovi katkaisee seinan kontuurissa (pystymaski pudottaa
oviaukon) → kaksi kollineaarista patkaa joiden valissa railo. Oven paalla on
aina ylitys (palkki ~2m→katto) → railo sillotaan ja aukkodetektio nakee oven.
5/8 GT-ovesta jai talo35:ssa loytymatta juuri taman takia."""
import numpy as np
import open3d 
import pytest

from ordinate.core.semantics.wall_semantics import bridge_lintel_gaps
from ordinate.schemas.model import ElementSource, Wall

_RNG = np.random.RandomState(7)


def _wall(wid, x0, x1, y=0.0):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y], [x1, y]], height=2700.0, thickness=120.0, z_min=0.0,
    )


def _lintel_pts(x0, x1, y=0.0, z0=2100.0, z1=2600.0, n=800):
    return np.column_stack([
        _RNG.uniform(x0, x1, n),
        y + _RNG.normal(0, 30.0, n),
        _RNG.uniform(z0, z1, n),
    ])


def _face_pts(x0, x1, y_face=60.0, n=3000):
    return np.column_stack([
        _RNG.uniform(x0, x1, n),
        y_face + _RNG.normal(0, 2.0, n),
        _RNG.uniform(300, 2400, n),
    ])


def test_door_gap_with_lintel_bridged():
    walls = [_wall("a", 0, 3000), _wall("b", 3900, 7000)]
    pts = np.vstack([_lintel_pts(3000, 3900), _face_pts(0, 3000), _face_pts(3900, 7000)])
    out = bridge_lintel_gaps(walls, pts)
    assert len(out) == 1, f"railoa ei sillottu ({len(out)} seinaa)"
    xs = sorted([out[0].axis[0][0], out[0].axis[1][0]])
    assert xs[0] <= 10 and xs[1] >= 6990, f"janne vajaa: {out[0].axis}"


def test_gap_without_lintel_not_bridged():
    walls = [_wall("a", 0, 3000), _wall("b", 3900, 7000)]
    pts = np.vstack([_face_pts(0, 3000), _face_pts(3900, 7000)])
    out = bridge_lintel_gaps(walls, pts)
    assert len(out) == 2, "railo sillottiin ilman ylitysevidenssia"


def test_closed_door_leaf_still_bridged():
    """Suljettu ovi: lehti tayttaa railon lattiakaistan (±50mm akselista) —
    silti sillattava, koska ylitys todistaa railon olevan saman seinan aukko
    (talo35: kaikki ovet skannattu kiinni)."""
    walls = [_wall("a", 0, 3000), _wall("b", 3900, 7000)]
    pts = np.vstack([
        _lintel_pts(3000, 3900),
        _lintel_pts(3000, 3900, z0=300.0, z1=2000.0, n=2000),
        _face_pts(0, 3000), _face_pts(3900, 7000),
    ])
    out = bridge_lintel_gaps(walls, pts)
    assert len(out) == 1, "suljetun oven railo jai sillottamatta"


def test_wide_gap_not_bridged():
    walls = [_wall("a", 0, 3000), _wall("b", 5900, 9000)]
    pts = np.vstack([_lintel_pts(3000, 5900), _face_pts(0, 3000), _face_pts(5900, 9000)])
    out = bridge_lintel_gaps(walls, pts)
    assert len(out) == 2, "2.9m railo ei ole ovi"

def test_jogged_wall_lines_not_bridged():
    """GT-jog: seinalinja porrastuu 60mm railon kohdalla — pinnat eri tasoilla
    → EI sama seina, silta tuottaisi kymmenien mm virheen puolelle jannetta."""
    walls = [_wall("a", 0, 3000), _wall("b", 3900, 7000)]
    pts = np.vstack([
        _lintel_pts(3000, 3900),
        _face_pts(0, 3000, y_face=60.0),
        _face_pts(3900, 7000, y_face=120.0),
    ])
    out = bridge_lintel_gaps(walls, pts)
    assert len(out) == 2, "porrastettu linja sillottiin"

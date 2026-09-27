"""close_open_corners: closes corners by extending open ends — must never
collapse a wall by pulling both ends inward to the same intersection.

Regression: two perpendicular stubs crossing mid-wall paired with BOTH open
ends of a 2m+ wall -> both ends moved to the same point -> zero-length wall."""
import numpy as np

from ordinate.core.semantics.corner_snap import close_open_corners
from ordinate.schemas.model import ElementSource, Wall


def _wall(wid, x0, y0, x1, y1):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=200.0, z_min=0.0,
    )


def _length(w):
    return float(np.hypot(w.axis[1][0] - w.axis[0][0], w.axis[1][1] - w.axis[0][1]))


def test_close_does_not_collapse_wall_between_crossing_stubs():
    walls = [
        _wall("mid", 0, 0, 2000, 0),
        _wall("stub_up", 1000, 100, 1000, 800),
        _wall("stub_down", 1000, -100, 1000, -800),
    ]
    out = close_open_corners(walls)
    mid = next(w for w in out if w.id == "mid")
    assert _length(mid) >= 1400.0, f"seina kutistui {_length(mid):.0f}mm:iin"


def test_close_still_closes_real_corner():
    walls = [
        _wall("a", 0, 0, 1800, 0),
        _wall("b", 2000, 200, 2000, 2000),
    ]
    out = close_open_corners(walls)
    a = next(w for w in out if w.id == "a")
    b = next(w for w in out if w.id == "b")
    assert np.allclose(a.axis[1], [2000, 0], atol=1.0), f"nurkka ei sulkeutunut: {a.axis[1]}"
    assert np.allclose(b.axis[0], [2000, 0], atol=1.0), f"nurkka ei sulkeutunut: {b.axis[0]}"

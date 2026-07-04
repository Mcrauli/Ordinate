"""_trim_endpoints: trimming is evidence-based but must never collapse a wall.

Regression: a perimeter wall with no scan data on its own faces picked up the
points of a CROSSING perpendicular wall (within the +-30mm face band at the
intersection) -> 2%/98% percentiles collapsed a 4m wall to 79mm."""
import numpy as np

from scan2bim.core.pipeline import _trim_endpoints
from scan2bim.schemas.model import ElementSource, Wall


def _wall(x0, y0, x1, y1, method="floorplan"):
    return Wall(
        id="w", confidence=1.0, classification="wall",
        source=ElementSource(method=method),
        axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=200.0, z_min=0.0,
    )


def _crossing_cluster(x=1500.0):
    rng = np.random.RandomState(0)
    n = 200
    return np.column_stack([
        rng.uniform(x - 60, x + 60, n),
        rng.uniform(-110, 110, n),
        rng.uniform(0, 2700, n),
    ])


def test_trim_does_not_collapse_wall_to_crossing():
    wall = _wall(0, 0, 3000, 0)
    out = _trim_endpoints(wall, _crossing_cluster())
    p0, p1 = np.array(out.axis[0]), np.array(out.axis[1])
    length = float(np.linalg.norm(p1 - p0))
    assert length >= 2400.0, f"seina romahti {length:.0f}mm:iin risteyspisteista"


def test_trim_still_trims_real_overshoot():
    rng = np.random.RandomState(1)
    n = 4000
    pts = np.column_stack([
        rng.uniform(0, 2800, n),
        np.where(rng.rand(n) < 0.5, -100.0, 100.0) + rng.normal(0, 3, n),
        rng.uniform(0, 2700, n),
    ])
    wall = _wall(0, 0, 3000, 0, method="contour")
    out = _trim_endpoints(wall, pts)
    p1 = np.array(out.axis[1])
    assert p1[0] < 2900.0, "aito ylitys jai trimmaamatta"

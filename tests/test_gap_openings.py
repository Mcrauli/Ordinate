"""Ovi kahden seinapatkan valissa.

Keilatussa myymalassa seina katkesi oven kohdalta kahdeksi patkaksi, ja
toisen patkan akseli oli 155 mm sivussa. Aukkohaku kulkee vain seinan
omalla janalla, joten ovi jai loytymatta, vaikka pinta jatkuu raon
molemmin puolin ja oven paalla on ylitys.
"""
import numpy as np

from ordinate.core.segmentation.opening_detector import detect_openings, openings_in_wall_gaps
from ordinate.schemas.model import ElementSource, Wall


class _Cloud:
    def __init__(self, pts):
        self.points = pts


def _wall(wid, x0, x1, y, th):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="contour"),
                axis=[[x0, y], [x1, y]], height=3500.0, thickness=th, z_min=0.0)


def _scene(door=(3000.0, 3900.0), head=2100.0, b_start=3900.0, seed=5):
    rng = np.random.RandomState(seed)
    n = 260000
    x = rng.uniform(0, 5500, n)
    z = rng.uniform(0, 3500, n)
    keep = ~((x > door[0]) & (x < door[1]) & (z < head))
    x, z = x[keep], z[keep]
    y = 60.0 + rng.normal(0, 2.0, len(x))
    walls = [_wall("a", 0.0, 3000.0, 0.0, 120.0), _wall("b", b_start, 5500.0, -160.0, 200.0)]
    return walls, _Cloud(np.column_stack([x, y, z]))


def test_door_between_segments_is_found_and_wall_closed():
    walls, cloud = _scene()
    assert detect_openings(walls, cloud, floor_z=0.0) == []
    new_walls, ops = openings_in_wall_gaps(walls, cloud, 0.0, [])
    assert len(ops) == 1, f"aukkoja {len(ops)}"
    op = ops[0]
    assert op.wall_id == "a" and op.opening_type == "door"
    assert abs(op.position_along - 3000.0) < 15.0, op.position_along
    assert abs(op.width - 900.0) < 25.0, op.width
    a = next(w for w in new_walls if w.id == "a")
    assert abs(a.axis[1][0] - 3900.0) < 1.0, a.axis


def test_gap_without_lintel_is_not_a_door():
    walls, cloud = _scene(head=3600.0)
    new_walls, ops = openings_in_wall_gaps(walls, cloud, 0.0, [])
    assert ops == []
    assert new_walls[0].axis == walls[0].axis


def test_narrow_gap_is_not_a_door():
    walls, cloud = _scene(door=(3000.0, 3620.0), b_start=3620.0)
    _, ops = openings_in_wall_gaps(walls, cloud, 0.0, [])
    assert ops == []

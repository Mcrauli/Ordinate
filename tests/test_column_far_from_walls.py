"""Pilaridetektion seinäetäisyysportti: indeksoitu versio = vanha tulos."""
from __future__ import annotations

import numpy as np

from ordinate.core.segmentation.column_detector import (
    _WALL_MARGIN, _dist_to_walls, _far_from_walls,
)
from ordinate.schemas.model import ElementSource, Wall


def _walls(rng, k: int) -> list[Wall]:
    out = []
    for i in range(k):
        a = rng.uniform(0, 40_000, 2)
        b = a + rng.normal(0, 6_000, 2)
        out.append(Wall(id=f"w{i}", confidence=0.9, source=ElementSource(method="contour"),
                        axis=[a.tolist(), b.tolist()], height=2700.0,
                        thickness=float(rng.choice([66.0, 120.0, 200.0])), z_min=0.0))
    return out


def test_same_decision_as_full_distance() -> None:
    rng = np.random.default_rng(3)
    walls = _walls(rng, 60)
    xy = rng.uniform(-2_000, 42_000, (200_000, 2))
    # tihennä pisteitä juuri rajan kohdalle, jossa ero näkyisi
    for w in walls[:20]:
        a, b = np.array(w.axis[0]), np.array(w.axis[1])
        t = rng.uniform(0, 1, 2_000)[:, None]
        u = (b - a) / max(np.linalg.norm(b - a), 1.0)
        nrm = np.array([-u[1], u[0]])
        off = w.thickness / 2 + _WALL_MARGIN + rng.uniform(-5, 5, 2_000)
        xy = np.vstack([xy, a + t * (b - a) + nrm * off[:, None]])
    old = _dist_to_walls(xy, walls) > _WALL_MARGIN
    new = _far_from_walls(xy, walls, _WALL_MARGIN)
    assert np.array_equal(old, new)
    assert 0 < old.sum() < len(old)


def test_empty_inputs() -> None:
    assert _far_from_walls(np.zeros((3, 2)), [], _WALL_MARGIN).all()
    assert len(_far_from_walls(np.zeros((0, 2)), _walls(np.random.default_rng(0), 3),
                               _WALL_MARGIN)) == 0

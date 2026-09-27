"""Jäännösseinien id:t eivät saa törmätä mallissa jo oleviin.

Putki ajaa `find_residual_walls`in kahdesti (geometriaketjun sisällä ja sen
jälkeen). Kumpikin ajo numeroi nollasta, joten koulun kellarin mallissa oli
`wall_res_000…008` KAHTEEN kertaan — duplikaatti-id sekoittaa IFC:n, QA:n ja
labelointityökalut.
"""
from __future__ import annotations

import numpy as np

from ordinate.core.semantics.residual_walls import _to_walls


def _pairs(n: int) -> list:
    return [(np.array([0.0, i * 1000.0]), np.array([5000.0, i * 1000.0]), 120.0)
            for i in range(n)]


def test_ids_skip_taken() -> None:
    taken = {"wall_res_000", "wall_res_001", "wall_res_002"}
    walls = _to_walls(_pairs(3), 2700.0, 120.0, 0.0, taken=taken)
    ids = [w.id for w in walls]
    assert len(walls) == 3
    assert not (set(ids) & taken)
    assert ids == ["wall_res_003", "wall_res_004", "wall_res_005"]


def test_ids_unique_without_taken() -> None:
    walls = _to_walls(_pairs(4), 2700.0, 120.0, 0.0)
    ids = [w.id for w in walls]
    assert ids == ["wall_res_000", "wall_res_001", "wall_res_002", "wall_res_003"]
    assert len(set(ids)) == len(ids)

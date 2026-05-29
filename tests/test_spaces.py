"""derive_spaces-testit."""
from __future__ import annotations

import numpy as np
import pytest

from scan2bim.core.semantics.spaces import derive_spaces
from scan2bim.schemas.model import (
    StructuralModel, Slab, Wall, Space, ElementSource
)


# --------------------------------------------------------------------------- #
# Apufunktiot
# --------------------------------------------------------------------------- #

def _box_boundary(x0=0.0, y0=0.0, x1=6000.0, y1=4000.0) -> list[list[float]]:
    """Suljettu nelikulmainen polygoni."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _make_slab(slab_type: str, elevation: float) -> Slab:
    return Slab(
        id="slab-" + slab_type[:3],
        confidence=0.8,
        source=ElementSource(method="z_histogram"),
        slab_type=slab_type,
        boundary=_box_boundary(),
        elevation=elevation,
        thickness=150.0,
    )


def _make_wall(height: float = 2800.0) -> Wall:
    return Wall(
        id="wall-1",
        confidence=0.9,
        source=ElementSource(method="ransac"),
        axis=[[0.0, 0.0], [6000.0, 0.0]],
        height=height,
        thickness=200.0,
    )


# --------------------------------------------------------------------------- #
# Testit
# --------------------------------------------------------------------------- #

def test_no_slabs_returns_empty():
    model = StructuralModel()
    assert derive_spaces(model) == []


def test_floor_only_no_ceiling_uses_wall_height():
    floor = _make_slab("floor", 0.0)
    wall = _make_wall(height=2800.0)
    model = StructuralModel(slabs=[floor], walls=[wall])
    spaces = derive_spaces(model)
    assert len(spaces) == 1
    s = spaces[0]
    assert s.floor_z == pytest.approx(0.0, abs=1)
    assert s.ceiling_z == pytest.approx(2800.0, abs=50)


def test_floor_and_ceiling_gives_correct_height():
    floor = _make_slab("floor", 0.0)
    ceiling = _make_slab("ceiling", 2800.0)
    model = StructuralModel(slabs=[floor, ceiling])
    spaces = derive_spaces(model)
    assert len(spaces) == 1
    s = spaces[0]
    assert s.floor_z == pytest.approx(0.0, abs=1)
    assert s.ceiling_z == pytest.approx(2800.0, abs=50)


def test_space_boundary_matches_floor():
    floor = _make_slab("floor", 0.0)
    model = StructuralModel(slabs=[floor], walls=[_make_wall()])
    spaces = derive_spaces(model)
    assert len(spaces) == 1
    assert spaces[0].boundary == floor.boundary


def test_space_schema_valid():
    floor = _make_slab("floor", 0.0)
    ceiling = _make_slab("ceiling", 2800.0)
    model = StructuralModel(slabs=[floor, ceiling])
    spaces = derive_spaces(model)
    for sp in spaces:
        assert isinstance(sp, Space)
        assert 0.0 <= sp.confidence <= 1.0
        assert sp.ceiling_z > sp.floor_z


def test_multiple_floors():
    f1 = _make_slab("floor", 0.0)
    f2 = _make_slab("floor", 3500.0)
    c = _make_slab("ceiling", 3000.0)
    model = StructuralModel(slabs=[f1, f2, c], walls=[_make_wall(height=3000.0)])
    spaces = derive_spaces(model)
    # f1 saa katon (c.elevation > f1 + 500 → 3000 > 500)
    # f2 on yli c.elevation → fallback wall-height
    assert len(spaces) == 2

"""StructuralModel serialisointi, deserialisointi ja validointi."""
import json

import pytest

from ordinate.schemas.model import (
    Beam, BeamProfile, Column, ColumnProfile, Discarded, ElementSource,
    Metadata, Slab, Space, StructuralModel, Wall,
)


def make_wall(id="wall_001") -> Wall:
    return Wall(
        id=id, confidence=0.93,
        axis=[[0, 0], [5000, 0]], height=2800, thickness=200,
        source=ElementSource(method="ransac"),
    )


def make_slab(id="slab_001") -> Slab:
    return Slab(
        id=id, confidence=0.9, slab_type="floor",
        boundary=[[0,0],[5000,0],[5000,4000],[0,4000]],
        elevation=0, thickness=250,
        source=ElementSource(method="z_histogram"),
    )


def make_column(id="col_001") -> Column:
    return Column(
        id=id, confidence=0.85,
        location=[1000, 2000], base_z=0, height=2800,
        profile=ColumnProfile(shape="rect", width=300, depth=300),
        source=ElementSource(method="cluster"),
    )


def make_beam(id="beam_001") -> Beam:
    return Beam(
        id=id, confidence=0.8,
        axis=[[0,0,2700],[5000,0,2700]],
        profile=BeamProfile(width=200, height=400),
        source=ElementSource(method="cluster"),
    )


def make_space(id="space_001") -> Space:
    return Space(
        id=id, confidence=0.9,
        boundary=[[0,0],[5000,0],[5000,4000],[0,4000]],
        floor_z=0, ceiling_z=2800,
        source=ElementSource(method="manual"),
    )


def full_model() -> StructuralModel:
    return StructuralModel(
        walls=[make_wall()], slabs=[make_slab()],
        columns=[make_column()], beams=[make_beam()], spaces=[make_space()],
        metadata=Metadata(units="mm", source_file="test.e57", voxel_size=20),
    )


def test_wall_valid():
    w = make_wall()
    assert w.thickness == 200
    assert w.classification == "wall"
    assert 0 <= w.confidence <= 1


def test_confidence_out_of_range():
    with pytest.raises(Exception):
        Wall(id="x", confidence=1.5, axis=[[0,0],[1,0]], height=100,
             thickness=10, source=ElementSource(method="ransac"))


def test_model_summary():
    m = full_model()
    s = m.summary()
    assert "1 walls" in s
    assert "1 slabs" in s
    assert "1 columns" in s


def test_roundtrip_json():
    m = full_model()
    m2 = StructuralModel.model_validate(json.loads(m.model_dump_json()))
    assert len(m2.walls) == 1
    assert m2.walls[0].axis == [[0, 0], [5000, 0]]
    assert m2.slabs[0].slab_type == "floor"
    assert m2.columns[0].profile.shape == "rect"


def test_save_load(tmp_path):
    m = full_model()
    p = tmp_path / "model.json"
    m.save(p)
    m2 = StructuralModel.load(p)
    assert m2.walls[0].id == "wall_001"
    assert m2.beams[0].profile.height == 400


def test_empty_model():
    m = StructuralModel()
    assert m.summary().startswith("StructuralModel: 0 walls")

"""Seinätodisteet: mitattu vain kun pintaa on, ja taso erottuu sotkusta."""
from __future__ import annotations

import numpy as np
import open3d as o3d

from ordinate.core.qa.wall_evidence import measure_wall_evidence
from ordinate.schemas.model import ElementSource, StructuralModel, Wall


def _cloud(pts: np.ndarray) -> o3d.geometry.PointCloud:
    c = o3d.geometry.PointCloud()
    c.points = o3d.utility.Vector3dVector(pts.astype(np.float64))
    return c


def _wall(y: float) -> Wall:
    return Wall(id=f"w{int(y)}", confidence=0.9, source=ElementSource(method="contour"),
                axis=[[0.0, y], [4000.0, y]], height=2700.0, thickness=120.0, z_min=0.0)


def test_flat_face_is_measured_and_empty_band_is_none() -> None:
    rng = np.random.default_rng(0)
    n = 20000
    face = np.column_stack([rng.uniform(0, 4000, n), np.full(n, 60.0) + rng.normal(0, 2, n),
                            rng.uniform(0, 2700, n)])
    clutter = np.column_stack([rng.uniform(0, 4000, n), 5000.0 + rng.uniform(-250, 250, n),
                               rng.uniform(0, 2700, n)])
    m = StructuralModel(walls=[_wall(0.0), _wall(5000.0), _wall(20000.0)])
    measure_wall_evidence(m, _cloud(np.vstack([face, clutter])))
    flat_wall, messy, empty = m.walls
    assert flat_wall.evidence is not None and messy.evidence is not None
    assert empty.evidence is None
    assert flat_wall.evidence["flat"] < 0.2
    assert messy.evidence["flat"] > flat_wall.evidence["flat"] * 5
    assert set(flat_wall.evidence) == {"len", "logpts", "thick", "flat", "contrast",
                                       "hspan", "htop", "body", "topvar", "cover"}

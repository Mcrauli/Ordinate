"""ClutterFilter-testit."""
from __future__ import annotations

import numpy as np
import pytest
import open3d as o3d

from scan2bim.core.semantics.clutter import detect_clutter
from scan2bim.schemas.model import StructuralModel, Discarded


def _box_cloud(cx, cy, w, d, h, n, rng) -> np.ndarray:
    x = rng.uniform(cx - w/2, cx + w/2, n)
    y = rng.uniform(cy - d/2, cy + d/2, n)
    z = rng.uniform(0, h, n)
    return np.column_stack([x, y, z])


def test_empty_cloud_returns_discarded():
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
    result = detect_clutter(cloud, StructuralModel())
    assert isinstance(result, Discarded)
    assert result.clutter_cluster_count == 0


def test_detects_isolated_clusters_as_clutter():
    rng = np.random.default_rng(42)
    # Pienet irralliset klusterit (esim. kalusteet) kaukana seinistä
    box1 = _box_cloud(2000, 2000, 500, 400, 800, 200, rng)  # pöytä
    box2 = _box_cloud(3500, 1500, 300, 300, 1200, 150, rng)  # tuoli
    pts = np.vstack([box1, box2])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pts.astype(float))
    result = detect_clutter(cloud, StructuralModel(), eps_mm=120, min_points=20)
    assert result.clutter_cluster_count >= 1
    assert result.total_points > 0


def test_returns_discarded_object():
    rng = np.random.default_rng(5)
    pts = rng.uniform(0, 500, (300, 3))
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pts)
    result = detect_clutter(cloud, StructuralModel(), eps_mm=80, min_points=20)
    assert isinstance(result, Discarded)
    assert result.reason != ""

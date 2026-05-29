"""BeamDetector-testit synteettisellä pistepilvellä.

Palkit: 4000 mm pitkiä, 200 mm leveitä, 300 mm syviä, katto z=2800.
"""
from __future__ import annotations

import numpy as np
import pytest
import open3d as o3d

from scan2bim.core.segmentation.beam_detector import BeamDetector
from scan2bim.schemas.model import Beam


def _beam_pts(x0, x1, cy, z_bot, z_top, n, rng) -> np.ndarray:
    x = rng.uniform(x0, x1, n)
    y = rng.uniform(cy - 100, cy + 100, n)
    z = rng.uniform(z_bot, z_top, n)
    return np.column_stack([x, y, z])


def _make_cloud(
    ceiling_z: float = 2800.0,
    beam_depth: float = 300.0,
    n: int = 1200,       # riittävä tiheys jotta DBSCAN ei jaa palkkia
    rng: np.random.Generator | None = None,
) -> o3d.geometry.PointCloud:
    if rng is None:
        rng = np.random.default_rng(77)
    z_bot = ceiling_z - beam_depth
    b1 = _beam_pts(500, 4500, 1000, z_bot, ceiling_z, n, rng)
    b2 = _beam_pts(500, 4500, 3000, z_bot, ceiling_z, n, rng)
    pts = np.vstack([b1, b2])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pts.astype(np.float64))
    return cloud


def test_detect_returns_beams():
    cloud = _make_cloud()
    beams, _ = BeamDetector(sub_ceiling_mm=400, eps_mm=120, min_points=15).detect(cloud)
    assert len(beams) > 0


def test_detect_finds_two_beams():
    """Odotetaan 2 palkkia; harvalla datalla DBSCAN voi jakaa → tarkistetaan
    että löytyi vähintään 2 ja yhteensä vähintään 2 erillistä Y-positiota."""
    cloud = _make_cloud()
    beams, _ = BeamDetector(sub_ceiling_mm=400, eps_mm=120, min_points=15).detect(cloud)
    assert len(beams) >= 2, f"Löytyi alle 2 palkkia: {len(beams)}"
    # Kumpikin palkki eri Y-positiossa (~1000 ja ~3000)
    y_centers = sorted(set(
        round((b.axis[0][1] + b.axis[1][1]) / 2 / 500) * 500 for b in beams
    ))
    assert len(y_centers) >= 2, f"Molemmat palkit samassa Y-positiossa: {y_centers}"


def test_beam_schema_valid():
    cloud = _make_cloud()
    beams, _ = BeamDetector(sub_ceiling_mm=400, eps_mm=120, min_points=15).detect(cloud)
    for b in beams:
        assert isinstance(b, Beam)
        assert 0.0 <= b.confidence <= 1.0
        assert len(b.axis) == 2
        assert len(b.axis[0]) == 3
        assert b.profile.width > 0
        assert b.profile.height > 0


def test_beam_total_span():
    """Kummankin palkin segmentit kattavat X-välin 500–4500mm."""
    cloud = _make_cloud()
    beams, _ = BeamDetector(sub_ceiling_mm=400, eps_mm=120, min_points=15).detect(cloud)
    # Ryhmittele Y:n mukaan (pyöristys 500mm tarkkuudella)
    from collections import defaultdict
    groups: dict[int, list] = defaultdict(list)
    for b in beams:
        y_key = round((b.axis[0][1] + b.axis[1][1]) / 2 / 500)
        groups[y_key].append(b)
    for y_key, group in groups.items():
        all_x = [pt[0] for b in group for pt in b.axis]
        span = max(all_x) - min(all_x)
        assert span > 3000, f"Y-ryhmä {y_key}: X-kattavuus {span:.0f} mm < 3000"


def test_short_cluster_not_beam():
    """Alle min_length → ei palkki."""
    rng = np.random.default_rng(99)
    pts = rng.uniform(0, 300, (200, 3))
    pts[:, 2] += 2600  # katto-vyöhykkeessä
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pts)
    beams, _ = BeamDetector(sub_ceiling_mm=400, eps_mm=120, min_points=15).detect(cloud)
    assert len(beams) == 0


def test_empty_cloud():
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.zeros((0, 3)))
    beams, _ = BeamDetector().detect(cloud)
    assert beams == []

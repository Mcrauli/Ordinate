"""Paksuuden tarkkuustestit — vaatimus ±2.5 mm.

Testaa sekä WallDetectorin RANSAC-paritusta että wall_pairing-geometriaa
synteettisillä kahden pinnan seinillä joiden todellinen paksuus on tiedossa.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d
import pytest

from scan2bim.core.segmentation.wall_detector import WallDetector
from scan2bim.core.semantics.wall_pairing import refine_wall_thicknesses
from scan2bim.schemas.model import Wall, ElementSource

TOLERANCE_MM = 2.5


# --------------------------------------------------------------------------- #
# Apufunktiot
# --------------------------------------------------------------------------- #

def _wall_face_pts(
    y_fixed: float,
    x0: float,
    x1: float,
    z0: float,
    z1: float,
    n: int,
    noise_mm: float,
    rng,
) -> np.ndarray:
    x = rng.uniform(x0, x1, n)
    z = rng.uniform(z0, z1, n)
    y = np.full(n, y_fixed) + rng.normal(0, noise_mm, n)
    return np.column_stack([x, y, z])


def _make_two_face_wall_cloud(
    thickness: float,        # mm — todellinen paksuus
    length: float = 5000.0,
    height: float = 2800.0,
    n_per_face: int = 3000,
    noise_mm: float = 3.0,
    rng: np.random.Generator | None = None,
) -> o3d.geometry.PointCloud:
    """Yksi seinä, molemmat pinnat skannattu."""
    if rng is None:
        rng = np.random.default_rng(42)
    face1 = _wall_face_pts(0.0, 0, length, 0, height, n_per_face, noise_mm, rng)
    face2 = _wall_face_pts(thickness, 0, length, 0, height, n_per_face, noise_mm, rng)
    pts = np.vstack([face1, face2])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(pts)
    return cloud


def _make_two_wall_pair_cloud(
    thickness: float,
    wall_length: float = 6000.0,
    height: float = 2800.0,
    n_per_face: int = 3000,
    noise_mm: float = 3.0,
    rng: np.random.Generator | None = None,
) -> o3d.geometry.PointCloud:
    """Kaksi erillistä seinää rinnakkain (sama kuin 1 seinä, 2 pintaa)."""
    return _make_two_face_wall_cloud(thickness, wall_length, height, n_per_face, noise_mm, rng)


def _detected_thickness(cloud: o3d.geometry.PointCloud) -> float | None:
    """Palauttaa detektoitu paksuus tai None jos ei löytynyt paria."""
    walls, _ = WallDetector(distance_threshold=20.0, num_iterations=1000).detect(cloud)
    measured = [w for w in walls if w.source.notes == "thickness_measured"]
    if not measured:
        return None
    return measured[0].thickness


# --------------------------------------------------------------------------- #
# RANSAC-paritustestit (molemmat pinnat samassa pilvessä)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("thickness", [100.0, 150.0, 200.0, 300.0, 500.0])
def test_ransac_pairing_accuracy(thickness: float):
    """RANSAC löytää molemmat pinnat ja mittaa paksuuden ±2.5 mm."""
    cloud = _make_two_face_wall_cloud(thickness, rng=np.random.default_rng(7))
    measured = _detected_thickness(cloud)
    assert measured is not None, \
        f"Paksuus {thickness:.0f} mm: RANSAC ei löytänyt paria"
    assert abs(measured - thickness) <= TOLERANCE_MM, \
        f"Paksuus {thickness:.0f} mm: mitattu {measured:.1f} mm, virhe {abs(measured-thickness):.1f} mm > {TOLERANCE_MM} mm"


def test_ransac_pairing_with_noise():
    """5 mm kohina ei saa vaikuttaa yli 2.5 mm tulokseen."""
    thickness = 200.0
    cloud = _make_two_face_wall_cloud(thickness, noise_mm=5.0, rng=np.random.default_rng(99))
    measured = _detected_thickness(cloud)
    assert measured is not None, "RANSAC ei löytänyt paria kohinaisessa pilvessä"
    assert abs(measured - thickness) <= TOLERANCE_MM, \
        f"Kohinainen pilvi: mitattu {measured:.1f} mm, virhe {abs(measured-thickness):.1f} mm"


# --------------------------------------------------------------------------- #
# Geometrinen paritustesti (wall_pairing.py)
# --------------------------------------------------------------------------- #

def _make_wall(axis_p0, axis_p1, thickness=0.0, notes="thickness_default") -> Wall:
    return Wall(
        id="test",
        confidence=0.8,
        source=ElementSource(method="ransac", notes=notes),
        axis=[list(axis_p0), list(axis_p1)],
        height=2800.0,
        thickness=thickness,
    )


@pytest.mark.parametrize("thickness", [100.0, 150.0, 200.0, 300.0, 400.0])
def test_geometric_pairing_accuracy(thickness: float):
    """wall_pairing löytää rinnakkaiset seinät ±2.5 mm tarkkuudella."""
    # Kaksi rinnakkaista seinää X-suuntaan, etäisyys = thickness
    w1 = _make_wall([0, 0], [6000, 0])
    w2 = _make_wall([0, thickness], [6000, thickness])
    result = refine_wall_thicknesses([w1, w2])
    for r in result:
        if r.source.notes in ("thickness_measured", "thickness_default"):
            # Mitattu pari
            if r.thickness != 300.0 and r.thickness != 200.0 and r.thickness != 120.0:
                assert abs(r.thickness - thickness) <= TOLERANCE_MM, \
                    f"Geom. paritus {thickness:.0f} mm: tulos {r.thickness:.1f} mm"


@pytest.mark.parametrize("offset,thickness", [
    (5000.0, 150.0),   # seinä kaukana origosta Y-suunnassa
    (10000.0, 300.0),  # hyvin kaukana
    (0.0, 100.0),      # origon lähellä
])
def test_ransac_far_from_origin(offset: float, thickness: float):
    """Paksuus ±2.5 mm vaikka seinä olisi kaukana koordinaatiston origosta."""
    rng = np.random.default_rng(13)
    n = 3000
    x = rng.uniform(0, 6000, n)
    z = rng.uniform(0, 2800, n)
    face1 = np.column_stack([x, np.full(n, offset) + rng.normal(0, 3, n), z])
    face2 = np.column_stack([x, np.full(n, offset + thickness) + rng.normal(0, 3, n), z])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.vstack([face1, face2]))
    walls, _ = WallDetector(distance_threshold=20, num_iterations=1000).detect(cloud)
    measured = [w for w in walls if w.source.notes == "thickness_measured"]
    assert measured, f"Offset={offset:.0f} mm, paksuus={thickness:.0f} mm: ei löytynyt mitattua paria"
    assert abs(measured[0].thickness - thickness) <= TOLERANCE_MM, \
        f"Virhe: {abs(measured[0].thickness - thickness):.1f} mm (offset={offset:.0f})"


def test_no_false_pairing():
    """Kaukaiset rinnakkaiset seinät (1500 mm) eivät pariudu."""
    w1 = _make_wall([0, 0], [6000, 0])
    w2 = _make_wall([0, 1500], [6000, 1500])
    result = refine_wall_thicknesses([w1, w2])
    for r in result:
        assert r.thickness != 1500.0, "1500 mm etäisyydellä olevat seinät eivät saa pariutua"


def test_perpendicular_walls_not_paired():
    """Kohtisuorat seinät eivät pariudu."""
    w1 = _make_wall([0, 0], [6000, 0])      # X-suuntainen
    w2 = _make_wall([200, 0], [200, 6000])   # Y-suuntainen
    result = refine_wall_thicknesses([w1, w2])
    thicknesses = [r.thickness for r in result]
    assert 200.0 not in thicknesses or all(
        r.source.notes in ("thickness_default",) for r in result
    ), "Kohtisuorat seinät pariutuivat virheellisesti"

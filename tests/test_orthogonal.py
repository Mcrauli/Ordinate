"""fine_rotate_walls: aidosti vino seina (esim. 6°) hyvaksytaan kun evidenssi on
vahva (kaksi siistia pintaa, yhteneva kulma); sotkuinen kaista ei kierra yli 2.5°."""
import numpy as np

from scan2bim.core.semantics.orthogonal import fine_rotate_walls
from scan2bim.schemas.model import ElementSource, Wall

_RNG = np.random.RandomState(7)


def _wall(x0, y0, x1, y1):
    return Wall(
        id="w", confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=150.0, z_min=0.0,
    )


def _two_face_band(length=3500.0, skew_deg=6.0, half_t=75.0, n=4000):
    """Kaksi yhdensuuntaista pintaa jotka ovat skew_deg vinossa y-akseliin nahden.
    Seinaakseli annetaan PYSTYSUORANA x=0 (regularize_orthogonal on pakottanut sen)."""
    t = _RNG.uniform(0, length, n)
    face = np.where(_RNG.rand(n) < 0.5, -half_t, half_t)
    ang = np.radians(skew_deg)
    u = np.array([np.sin(ang), np.cos(ang)])      # seinan todellinen suunta
    nrm = np.array([np.cos(ang), -np.sin(ang)])
    pts2d = t[:, None] * u[None, :] + face[:, None] * nrm[None, :]
    pts2d += _RNG.normal(0, 3.0, pts2d.shape)      # 3mm pintakohina
    z = _RNG.uniform(200, 2500, n)
    return np.column_stack([pts2d[:, 0], pts2d[:, 1], z])


def test_strong_two_face_evidence_accepts_genuine_skew():
    pts = _two_face_band(skew_deg=6.0)
    w = _wall(0.0, 0.0, 0.0, 3500.0)   # akseli pakotettu pystyyn
    out = fine_rotate_walls([w], pts, z_min=100.0, z_max=2600.0)[0]
    (x0, y0), (x1, y1) = out.axis
    got_deg = np.degrees(np.arctan2(abs(x1 - x0), abs(y1 - y0)))
    assert got_deg > 4.5, f"vinoa seinaa ei hyvaksytty: kierto vain {got_deg:.1f} astetta"
    assert abs(got_deg - 6.0) < 1.0


def test_messy_band_does_not_over_rotate():
    """Kalusterivi = yksi sotkuinen pistejoukko vinossa → EI saa kiertaa yli 2.5°."""
    n = 4000
    t = _RNG.uniform(0, 3500.0, n)
    ang = np.radians(6.0)
    u = np.array([np.sin(ang), np.cos(ang)])
    pts2d = t[:, None] * u[None, :]
    pts2d += _RNG.normal(0, 55.0, pts2d.shape)     # leveä sotkuinen jakauma
    z = _RNG.uniform(200, 2500, n)
    pts = np.column_stack([pts2d[:, 0], pts2d[:, 1], z])
    w = _wall(0.0, 0.0, 0.0, 3500.0)
    out = fine_rotate_walls([w], pts, z_min=100.0, z_max=2600.0)[0]
    (x0, y0), (x1, y1) = out.axis
    got_deg = np.degrees(np.arctan2(abs(x1 - x0), abs(y1 - y0)))
    assert got_deg <= 2.6, f"sotkuinen kaista kiersi {got_deg:.1f} astetta"

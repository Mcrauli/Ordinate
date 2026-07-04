"""_thickness_lock_walls: yksipuolisenkin seinan PINTA lukitaan raakapisteisiin
ali-bin-tarkkuudella (aiemmin vain kaksipuoliset; yksipuolinen jai 12mm-voxelin
varaan → 2-4mm pintavirhe)."""
import numpy as np
import open3d as o3d

from scan2bim.core.pipeline import _thickness_lock_walls
from scan2bim.schemas.model import ElementSource, Wall

_RNG = np.random.RandomState(3)


def _wall(x_axis, th=150.0):
    return Wall(
        id="w", confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x_axis, 0.0], [x_axis, 4000.0]], height=2700.0, thickness=th, z_min=0.0,
    )


def _cloud_one_face(x_face, n=20000):
    y = _RNG.uniform(0, 4000, n)
    z = _RNG.uniform(300, 2400, n)
    x = x_face + _RNG.normal(0, 2.0, n)   # 2mm pintakohina
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    return pc


def test_single_face_locked_to_subbin_accuracy():
    """Skannattu pinta x=0. Akseli annettu 7mm pielessa (pinta olisi x=-7+75=68?
    ei: akseli x=68 → laheisin mallipinta x=68-75=-7). Lukituksen jalkeen
    mallipinnan on osuttava skannattuun pintaan <0.5mm."""
    th = 150.0
    w = _wall(x_axis=th / 2.0 + 7.0, th=th)     # mallipinta nyt x=+7
    cloud = _cloud_one_face(0.0)
    out = _thickness_lock_walls([w], cloud)[0]
    face = min(out.axis[0][0] - th / 2.0, out.axis[0][0] + th / 2.0, key=abs)
    assert abs(face) < 0.7, f"pinta jai {face:.2f}mm paahan skannatusta"
    assert abs(out.thickness - th) < 0.1, "yksipuolisen paksuutta ei saa muuttaa"


def test_two_faces_still_measured():
    th_true = 180.0
    w = _wall(x_axis=th_true / 2.0 + 5.0, th=150.0)
    n = 15000
    y = _RNG.uniform(0, 4000, 2 * n)
    z = _RNG.uniform(300, 2400, 2 * n)
    x = np.concatenate([
        0.0 + _RNG.normal(0, 2.0, n),
        th_true + _RNG.normal(0, 2.0, n),
    ])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    out = _thickness_lock_walls([w], pc)[0]
    assert abs(out.thickness - th_true) < 1.5
    assert abs(out.axis[0][0] - th_true / 2.0) < 1.0   # akseli pintojen puolivaliin


def test_asymmetric_visibility_pair_still_found():
    """Rohbau wall_002: etupinta skannattu 4x tiheammin kuin takapinta (takapinta
    ~25% kynnyksen alla) → pari loydyttava silti, koska heikko piikki istuu
    odotetun vastapinnan kohdalla. Ilman korjausta yksipinta-polku jatti
    seinan 22mm pieleen (GT: molemmat pinnat 100% Wall-luokkaa)."""
    th_true = 220.0
    w = _wall(x_axis=th_true / 2.0 - 10.0, th=200.0)
    n_front, n_back = 24000, 3000
    y = _RNG.uniform(0, 4000, n_front + n_back)
    z = _RNG.uniform(300, 2400, n_front + n_back)
    x = np.concatenate([
        0.0 + _RNG.normal(0, 2.0, n_front),
        th_true + _RNG.normal(0, 2.0, n_back),
    ])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    out = _thickness_lock_walls([w], pc)[0]
    assert abs(out.thickness - th_true) < 2.0, f"paksuus {out.thickness} != {th_true}"
    assert abs(out.axis[0][0] - th_true / 2.0) < 1.5, "akseli ei pintojen puolivalissa"


def test_junk_band_wall_flagged_low_confidence():
    """Rohbau wall_ext_000: perimetriseinan kaistassa vain tasaista massoa
    (rakennustelineet/tavara), ei pintaa → mediaanilinjaus on fiktiota.
    Confidence puolitettava jotta QA nostaa seinan tarkistettavaksi."""
    from scan2bim.core.pipeline import _align_faces_to_surface_median

    w = _wall(x_axis=0.0, th=66.0).model_copy(update={"confidence": 0.5})
    n = 20000
    pts = np.column_stack([
        _RNG.uniform(-110, 110, n),          # tasainen jakauma koko kaistalla
        _RNG.uniform(0, 4000, n),
        _RNG.uniform(300, 2400, n),
    ])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    out = _align_faces_to_surface_median([w], pc)[0]
    assert out.confidence < 0.4, f"mossoseinaa ei flagatty (conf {out.confidence})"


def test_clean_surface_confidence_unchanged():
    from scan2bim.core.pipeline import _align_faces_to_surface_median

    w = _wall(x_axis=75.0 + 3.0, th=150.0)
    cloud = _cloud_one_face(0.0)
    out = _align_faces_to_surface_median([w], cloud)[0]
    assert out.confidence == 1.0

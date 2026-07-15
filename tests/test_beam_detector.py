"""Palkkidetektio pipelinen kautta: palkki katon alla loytyy, seinan ylaosa EI
ole palkki (seinaeksluusio ennen klusterointia)."""
import numpy as np
import open3d as o3d

from scan2bim.core.segmentation.beam_detector import detect_beams
from scan2bim.schemas.model import ElementSource, Wall

_RNG = np.random.RandomState(11)


def _wall(wid, x0, y0, x1, y1, th=200.0):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=th, z_min=0.0,
    )


def _cloud(parts):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pc


def _beam_pts(x0, x1, y, w=200.0, z0=2300.0, z1=2650.0, n=4000):
    return np.column_stack([
        _RNG.uniform(x0, x1, n),
        _RNG.uniform(y - w / 2, y + w / 2, n),
        _RNG.uniform(z0, z1, n),
    ])


def _wall_face_pts(x0, x1, y, n=8000):
    return np.column_stack([
        _RNG.uniform(x0, x1, n),
        y + _RNG.normal(0, 3.0, n),
        _RNG.uniform(0, 2700, n),
    ])


def _ceiling_pts(n=20000):
    return np.column_stack([
        _RNG.uniform(0, 6000, n),
        _RNG.uniform(0, 5000, n),
        2700.0 + _RNG.normal(0, 3.0, n),
    ])


def test_beam_under_ceiling_found():
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    cloud = _cloud([
        _beam_pts(500, 5500, 2500),
        _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000),
        _ceiling_pts(),
    ])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0)
    assert len(beams) == 1, f"palkkeja {len(beams)}, odotettiin 1"
    L = np.hypot(beams[0].axis[1][0] - beams[0].axis[0][0],
                 beams[0].axis[1][1] - beams[0].axis[0][1])
    assert L > 4000, f"palkin pituus vajaa: {L:.0f}"


def test_wall_top_not_beam():
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    cloud = _cloud([
        _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000),
        _ceiling_pts(),
    ])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0)
    assert len(beams) == 0, f"seinan ylaosa tulkittiin palkiksi ({len(beams)} kpl)"


def test_hanging_mep_not_beam_in_finished_space():
    # Valmis tila (kattolaatta tiedossa): katosta 500mm alas roikkuva pitkanomainen
    # klusteri = talotekniikka (kanava/putki), EI palkki. Soffit-kiinnitystesti.
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    hanging = _beam_pts(500, 5500, 2500, w=200.0, z0=2050.0, z1=2200.0)  # laki 2200, katto 2700 -> vali 500mm
    cloud = _cloud([hanging, _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000), _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 0, f"roikkuva MEP tulkittiin palkiksi ({len(beams)} kpl)"


def test_soffit_attached_beam_found_in_finished_space():
    # Sama tila mutta palkki kiinni katossa (laki 2650, vali 50mm) -> aito palkki sailyy.
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    beam = _beam_pts(500, 5500, 2500, w=250.0, z0=2350.0, z1=2650.0)
    cloud = _cloud([beam, _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000), _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 1, f"kattoon kiinnittynyt palkki katosi ({len(beams)} kpl)"


def _clutter_column_pts(x, y, w=400.0, z0=100.0, z1=2650.0, n=15000):
    return np.column_stack([
        _RNG.uniform(x - w / 2, x + w / 2, n),
        _RNG.uniform(y - w / 2, y + w / 2, n),
        _RNG.uniform(z0, z1, n),
    ])


def test_beam_on_furniture_stack_not_beam():
    # Kattoon kiinnittynyt leveä klusteri MUTTA sen alla on tayskorkea kalustepatteri
    # (ei tyhjaa alla) -> ei vapaa palkki. Headroom-testi hylkaa. 3DSES-huoneen valepalkki.
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    beam = _beam_pts(500, 5500, 2500, w=250.0, z0=2350.0, z1=2650.0)
    clutter = np.vstack([_clutter_column_pts(x, 2500) for x in range(800, 5400, 350)])
    cloud = _cloud([beam, clutter, _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000), _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 0, f"kalustepatterin paalla oleva klusteri tulkittiin palkiksi ({len(beams)} kpl)"

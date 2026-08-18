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


# --------------------------------------------------------------------------- #
# Alapintamalli: palkki on kaksi pystypintaa ja niiden valinen alapinta, ei
# umpikappale. Naissa pisteet ovat PINNOILLA kuten oikeassa keilauksessa.
# --------------------------------------------------------------------------- #

def _beam_faces(x0, x1, y, w=300.0, z_soffit=2300.0, z_top=2680.0, step=25.0):
    """Palkin kaksi kylkea ja alapinta pintapisteina."""
    x = np.arange(x0, x1, step)
    z = np.arange(z_soffit, z_top, step)
    xx, zz = np.meshgrid(x, z)
    sides = [np.column_stack([xx.ravel(), np.full(xx.size, y + s * w / 2), zz.ravel()])
             for s in (-1, 1)]
    yy = np.arange(y - w / 2, y + w / 2 + step, step)
    gx, gy = np.meshgrid(x, yy)
    soffit = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, z_soffit)])
    return np.vstack(sides + [soffit])


def _riser_faces(x, y, w=300.0, z0=0.0, z1=2680.0, step=25.0):
    """Hormi: tayskorkea pystykotelo lattiasta kattoon."""
    z = np.arange(z0, z1, step)
    a = np.arange(-w / 2, w / 2 + step, step)
    aa, zz = np.meshgrid(a, z)
    out = []
    for s in (-1, 1):
        out.append(np.column_stack([x + aa.ravel(), np.full(aa.size, y + s * w / 2), zz.ravel()]))
        out.append(np.column_stack([np.full(aa.size, x + s * w / 2), y + aa.ravel(), zz.ravel()]))
    return np.vstack(out)


def test_beam_width_comes_from_the_soffit_not_from_one_face():
    """Kaksi pystypintaa 300 mm erillaan = YKSI 300 mm palkki.

    Vanha klusterimalli antoi joko 143 mm (yksi pinta) tai koko palkiston
    leveyden. Leveys mitataan alapinnasta, joka yhdistaa kyljet.
    """
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    cloud = _cloud([_beam_faces(500, 5500, 2500),
                    _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000),
                    _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 1, f"palkkeja {len(beams)}, odotettiin 1"
    w = beams[0].profile.width
    assert 250 <= w <= 700, f"leveys {w:.0f} ei ole palkin leveys"


def test_riser_reaching_the_floor_is_not_a_beam():
    """Asunnon hormi: pitkanomainen ja kiinni katossa, mutta yltaa lattiaan.

    Tama on se tapaus jota vanha malli ei saanut pois kolmella eri saannolla.
    Alapintaehto hoitaa sen ilman omaa saantoa: hormin alin piste on lattialla.
    """
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    riser = np.vstack([_riser_faces(x, 2500) for x in (1500.0, 1800.0, 2100.0, 2400.0)])
    cloud = _cloud([riser, _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000),
                    _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 0, f"hormi tulkittiin palkiksi ({len(beams)} kpl)"


def test_column_break_does_not_split_the_beam_in_two():
    """Pilari katkaisee alapinnan; palkki on silti yksi jasen."""
    walls = [_wall("w0", 0, 0, 8000, 0), _wall("w1", 0, 5000, 8000, 5000)]
    cloud = _cloud([_beam_faces(500, 3400, 2500), _beam_faces(4000, 7500, 2500),
                    _wall_face_pts(0, 8000, 0), _wall_face_pts(0, 8000, 5000),
                    _ceiling_pts(n=30000)])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 1, f"palkki pilkkoutui {len(beams)} osaan"
    L = np.hypot(beams[0].axis[1][0] - beams[0].axis[0][0],
                 beams[0].axis[1][1] - beams[0].axis[0][1])
    assert L > 6500, f"yhdistetty pituus vajaa: {L:.0f}"


def test_far_apart_collinear_beams_stay_separate():
    """Sama linja mutta 6 m vali -> kaksi palkkia, ei yhta venytettya.

    Seinapuolella tama sama venytys jouduttiin leikkaamaan pois jalkikateen
    (`semantics/overstretch.py`); palkeissa sita ei paasteta syntymaan.
    """
    walls = [_wall("w0", 0, 0, 16000, 0), _wall("w1", 0, 5000, 16000, 5000)]
    cloud = _cloud([_beam_faces(500, 4000, 2500), _beam_faces(10000, 15500, 2500),
                    _wall_face_pts(0, 16000, 0), _wall_face_pts(0, 16000, 5000),
                    _ceiling_pts(n=40000)])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 2, f"erillaan olevat palkit yhdistyivat ({len(beams)} kpl)"


def test_lowered_ceiling_area_is_not_a_beam():
    """Leveä alaslasku ei ole palkki — aspektiportti."""
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 5000, 6000, 5000)]
    x = np.arange(1000.0, 5000.0, 25.0)
    y = np.arange(1000.0, 4000.0, 25.0)
    xx, yy = np.meshgrid(x, y)
    drop = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, 2350.0)])
    cloud = _cloud([drop, _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000),
                    _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 0, f"alaslaskettu katto tulkittiin palkiksi ({len(beams)} kpl)"


def test_beam_on_the_wall_line_belongs_to_the_wall():
    """Seinalinjalla oleva alapinta on seinan ylaosa (tai palkin ja seinan
    yhteinen), ei erillinen palkki — muuten jokainen seina saisi palkin."""
    walls = [_wall("w0", 0, 2500, 6000, 2500)]
    cloud = _cloud([_beam_faces(500, 5500, 2500),
                    _wall_face_pts(0, 6000, 0), _wall_face_pts(0, 6000, 5000),
                    _ceiling_pts()])
    beams = detect_beams(cloud, walls, floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 0, f"seinalinjan alapinta tulkittiin palkiksi ({len(beams)} kpl)"


def test_duct_turning_a_corner_is_not_a_beam():
    """Kulmassa kaantyva kanava: pitkanomainen (aspekti 5.4) mutta laikku
    tayttaa vain 31 % suorakaiteestaan. Palkin alapinta on tayssuorakaide.
    Mitattu Rohbaussa tarkkuutena 0.808 -> 0.834 samalla kattavuudella."""
    walls = [_wall("w0", 0, 0, 16000, 0), _wall("w1", 0, 9000, 16000, 9000)]
    arm_x = _beam_faces(1000, 13000, 2500, w=300.0)
    y = np.arange(2650.0, 4300.0, 25.0)
    z = np.arange(2300.0, 2680.0, 25.0)
    yy, zz = np.meshgrid(y, z)
    sides = [np.column_stack([np.full(yy.size, 12500.0 + s * 150.0), yy.ravel(), zz.ravel()])
             for s in (-1, 1)]
    xg = np.arange(12350.0, 12650.0, 25.0)
    gx, gy = np.meshgrid(xg, y)
    arm_y = np.vstack(sides + [np.column_stack([gx.ravel(), gy.ravel(),
                                                np.full(gx.size, 2300.0)])])
    ceil = np.column_stack([_RNG.uniform(0, 16000, 80000), _RNG.uniform(0, 9000, 80000),
                            2700.0 + _RNG.normal(0, 3.0, 80000)])
    beams = detect_beams(_cloud([arm_x, arm_y, ceil]), walls,
                         floor_z=0.0, ceiling_z=2700.0, has_ceiling=True)
    assert len(beams) == 0,         f"kulmakanava tulkittiin palkiksi: {[(b.profile.width, b.profile.height) for b in beams]}"


def test_deep_beam_in_a_tall_hall_is_found():
    """Syvyysraja skaalautuu tilan korkeudesta.

    Rohbau site_07:n palkit ovat 2.6 m syvia eli kiinni kiinteassa 3000 mm
    rajassa; seuraavan hallin syvempi palkisto olisi pudonnut kokonaan.
    """
    walls = [_wall("w0", 0, 0, 12000, 0), _wall("w1", 0, 9000, 12000, 9000)]
    beam = _beam_faces(1000, 11000, 4500, w=800.0, z_soffit=8000.0, z_top=11950.0, step=60.0)
    ceil = np.column_stack([_RNG.uniform(0, 12000, 60000), _RNG.uniform(0, 9000, 60000),
                            12000.0 + _RNG.normal(0, 3.0, 60000)])
    beams = detect_beams(_cloud([beam, ceil]), walls,
                         floor_z=0.0, ceiling_z=12000.0, has_ceiling=True)
    assert len(beams) == 1, f"syva palkki korkeassa hallissa katosi ({len(beams)} kpl)"
    assert beams[0].profile.height > 3000, f"syvyys {beams[0].profile.height:.0f}"

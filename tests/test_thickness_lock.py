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


def test_clutter_face_rejected_by_ceiling_in_body():
    """Yksipuolinen ulkoseina x=0 (vain sisapinta keilattu) + kaappi 300mm
    huoneen sisalla x=-300. Pari antaisi 300mm paksuuden ja siirtaisi akselin
    150mm huoneeseen → naapuripatka jaa eri linjalle eika sulaudu (mitattu apt2:
    huone 33 m2 katosi). KATTO nakyy kaapin PAALLA eli rungon sisalla → hylkaa
    pari ja mittaa vain nakyva pinta."""
    # virhetila kuten tuotannossa: akseli JO valeparin puolivalissa (t=330)
    clutter_x = -330.0
    w = _wall(x_axis=clutter_x / 2.0, th=-clutter_x)
    # seinapinta on tiheampi kuin kaluste (mitattu asunnolla 560k vs 171k = 3.3x)
    n_face, n_clut = 24000, 7000
    face = np.column_stack([_RNG.normal(0, 2.0, n_face),
                            _RNG.uniform(0, 4000, n_face), _RNG.uniform(300, 2400, n_face)])
    clut = np.column_stack([clutter_x + _RNG.normal(0, 2.0, n_clut),
                            _RNG.uniform(0, 4000, n_clut), _RNG.uniform(300, 2400, n_clut)])
    # katto koko huoneen ylla, MYOS kaapin paalla (x=-330..0) = rungon sisalla
    m = 40000
    ceil = np.column_stack([
        _RNG.uniform(-2000, 0, m), _RNG.uniform(0, 4000, m),
        2700.0 + _RNG.normal(0, 2.0, m),
    ])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack([face, clut]))

    ilman = _thickness_lock_walls([w], pc, ceiling_xy=None)[0]
    assert abs(ilman.thickness - 330.0) < 3.0, \
        f"testi ei toista virhetta: paksuus {ilman.thickness}"

    out = _thickness_lock_walls([w], pc, ceiling_xy=ceil[:, :2])[0]
    assert abs(out.thickness - 200.0) < 1.0, \
        f"valeparia ei hylatty: paksuus {out.thickness}"
    seen = min(out.axis[0][0] - out.thickness / 2.0,
               out.axis[0][0] + out.thickness / 2.0, key=abs)
    assert abs(seen) < 1.0, f"nakyva pinta jai {seen:.2f}mm paahan"
    assert out.axis[0][0] > 0.0, "runko kasvoi huoneen puolelle"


def test_real_thick_pair_kept_when_body_empty():
    """Aito 300mm seina: runko on umpinainen (ei kattoa sisalla) → pari kelpaa."""
    th_true = 300.0
    w = _wall(x_axis=th_true / 2.0 + 6.0, th=250.0)
    n = 16000
    y = _RNG.uniform(0, 4000, 2 * n); z = _RNG.uniform(300, 2400, 2 * n)
    x = np.concatenate([_RNG.normal(0, 2.0, n), th_true + _RNG.normal(0, 2.0, n)])
    m = 40000
    ceil = np.column_stack([                       # kattoa vain rungon ULKOpuolella
        np.concatenate([_RNG.uniform(-2000, -20, m // 2),
                        _RNG.uniform(th_true + 20, th_true + 2000, m // 2)]),
        _RNG.uniform(0, 4000, m), 2700.0 + _RNG.normal(0, 2.0, m),
    ])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    out = _thickness_lock_walls([w], pc, ceiling_xy=ceil[:, :2])[0]
    assert abs(out.thickness - th_true) < 1.5, f"aito pari hylattiin: {out.thickness}"


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


def test_unsupported_thin_thickness_becomes_one_sided():
    """Synteettinen 72x48 m myymala: yksipuolisen pinnan maskiviivan kontuuri
    kiertaa viivan MOLEMMILTA puolilta, ja _merge_axis_lines luki reunat kahdeksi
    pinnaksi -> 92 mm "seina" johon raakapisteissa on vain YKSI pinta. Vanha +-60 mm
    ikkuna ei ylla valepaksuuden yli, joten seina jai korjaamatta 57-62 mm
    pieleen (mitattu _tol_heatmap:lla). Nyt: paksuus yksipuolisen oletukseksi ja
    NAKYVA pinta mitatulle tasolle."""
    th_fake = 92.0
    # Ainoa pinta x=0. Akseli 46 mm siita -> mallipinnat x=0-46+-46 = -92 ja 0?
    # ei: akseli x=-46, pinnat x=-92 ja x=0 -> osuisi. Siirretaan kuten oikeassa
    # ajossa: akseli 103 mm pinnan takana, jolloin lahin mallipinta on 57 mm
    # pielessa eika mahdu +-60 mm ikkunaan yhdessakaan iteraatiossa.
    w = _wall(x_axis=-115.0, th=th_fake)
    n = 20000
    y = _RNG.uniform(0, 4000, n)
    z = _RNG.uniform(300, 2400, n)
    face_pts = np.column_stack([_RNG.normal(0, 2.0, n), y, z])
    # Sisatilan massa selvasti pinnan +x-puolella mutta hakukaistan (+-200 mm)
    # ULKOPUOLELLA -> ei toista huippua, mutta massakeskipiste kertoo suunnan.
    room = np.column_stack([
        _RNG.uniform(1000, 5000, n), _RNG.uniform(0, 4000, n), _RNG.uniform(0, 2700, n),
    ])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack([face_pts, room]))
    out = _thickness_lock_walls([w], pc)[0]
    assert out.thickness == 200.0, f"valepaksuus jai voimaan: {out.thickness}"
    face = min(out.axis[0][0] - out.thickness / 2.0,
               out.axis[0][0] + out.thickness / 2.0, key=abs)
    assert abs(face) < 1.0, f"nakyva pinta {face:.1f} mm pielessa"
    assert out.axis[0][0] < 0.0, "runko kasvoi huoneeseen pain, ei ulos"


def test_supported_thin_wall_keeps_its_thickness():
    """Aito 66 mm valiseina jonka MOLEMMAT pinnat nakyvat: paksuutta ei saa
    korvata yksipuolisen oletuksella."""
    th_true = 66.0
    w = _wall(x_axis=th_true / 2.0 + 4.0, th=th_true)
    n = 12000
    y = _RNG.uniform(0, 4000, 2 * n)
    z = _RNG.uniform(300, 2400, 2 * n)
    x = np.concatenate([_RNG.normal(0, 2.0, n), th_true + _RNG.normal(0, 2.0, n)])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    out = _thickness_lock_walls([w], pc)[0]
    assert abs(out.thickness - th_true) < 2.0, f"aito ohut seina paisui {out.thickness}"


def test_one_sided_wall_corrected_beyond_25mm_cap():
    """Synteettinen myymala: 72 m ulkoseina jai 57.4 mm pinnastaan koska
    _align_faces_to_surface_median MITTASI virheen oikein mutta 25 mm cap esti
    korjauksen. Cap oletti etta akseli on jo ~oikein - se pitaa kaksipuoliselle
    (pinnat kiinnittavat sen), ei yksipuoliselle."""
    from scan2bim.core.pipeline import _align_faces_to_surface_median

    th = 92.0
    w = _wall(x_axis=-57.0, th=th)          # ainoa pinta x=0, mallipinta x=-11
    cloud = _cloud_one_face(0.0)
    out = _align_faces_to_surface_median([w], cloud)[0]
    face = min(out.axis[0][0] - th / 2.0, out.axis[0][0] + th / 2.0, key=abs)
    assert abs(face) < 1.5, f"pinta jai {face:.1f} mm paahan"


def test_two_sided_wall_keeps_the_25mm_cap():
    """Kaksipuolisella seinalla iso siirto tarkoittaa VAARAA pintaa - cappia ei
    saa loysata silla akselin kiinnittaa kaksi pintaa."""
    from scan2bim.core.pipeline import _align_faces_to_surface_median

    th = 200.0
    w = _wall(x_axis=th / 2.0 + 60.0, th=th)   # akseli 60 mm pielessa
    n = 15000
    y = _RNG.uniform(0, 4000, 2 * n)
    z = _RNG.uniform(300, 2400, 2 * n)
    x = np.concatenate([_RNG.normal(0, 2.0, n), th + _RNG.normal(0, 2.0, n)])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.column_stack([x, y, z]))
    out = _align_faces_to_surface_median([w], pc)[0]
    assert out.axis[0][0] == w.axis[0][0], "kaksipuolista siirrettiin cappia enemman"

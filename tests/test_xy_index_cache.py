"""Indeksointi ei saa muuttaa tulosta — vain nopeutta.

Kaksi nopeusmuutosta lepää tämän varassa: pilvikohtainen indeksivälimuisti
(22 rakennusta → 4) ja kiertopassien kaistahaku (`fine_rotate_walls`,
`refine_skew_walls`). Molempien on tuotettava BITILLEEN sama akseli kuin koko
pistetaulukon skannaus, muuten kyseessä ei ole nopeutus vaan muutos.
"""
import numpy as np
import pytest

from ordinate.core.geometry.xy_index import XYIndex, clear_index_cache, index_for
from ordinate.core.semantics.orthogonal import fine_rotate_walls, refine_skew_walls
from ordinate.schemas.model import ElementSource, Wall

_H = 2700.0


def _wall(wid, a, b, thickness=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[list(a), list(b)], height=_H, thickness=thickness, z_min=0.0)


def _face(a, b, step=12.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    t = np.arange(0.0, L, step) / L
    xy = a + (b - a) * t[:, None]
    zs = np.arange(300.0, _H - 300.0, step)
    out = np.repeat(xy, len(zs), axis=0)
    return np.column_stack([out, np.tile(zs, len(xy))])


def _scene():
    """Pilvi jossa on suora seinä, hieman vinossa oleva ja aidosti vino."""
    rng = np.random.default_rng(7)
    parts = []
    for a, b in (((0.0, 0.0), (14000.0, 0.0)),
                 ((0.0, 200.0), (14000.0, 200.0)),
                 ((0.0, 6000.0), (13000.0, 6400.0)),
                 ((0.0, 6200.0), (13000.0, 6600.0)),
                 ((2000.0, 12000.0), (12000.0, 13200.0)),
                 ((2000.0, 12200.0), (12000.0, 13400.0))):
        parts.append(_face(a, b))
    pts = np.vstack(parts)
    pts += rng.normal(0.0, 2.0, pts.shape)
    return pts


def _axes(walls):
    return [tuple(map(tuple, w.axis)) for w in walls]


@pytest.fixture(scope="module")
def scene():
    pts = _scene()
    assert len(pts) > 300_000, len(pts)
    return pts


def _walls():
    return [_wall("suora", (0.0, 100.0), (14000.0, 100.0)),
            _wall("kalteva", (0.0, 6100.0), (13000.0, 6500.0)),
            _wall("vino", (2000.0, 12100.0), (12000.0, 12100.0))]


def test_fine_rotate_is_bit_identical_with_an_index(scene):
    idx = XYIndex(scene)
    a = fine_rotate_walls(_walls(), scene, z_min=500.0, z_max=2400.0)
    b = fine_rotate_walls(_walls(), scene, z_min=500.0, z_max=2400.0, index=idx)
    assert _axes(a) == _axes(b)


def test_refine_skew_is_bit_identical_with_an_index(scene):
    idx = XYIndex(scene)
    a = refine_skew_walls(_walls(), scene, z_min=500.0, z_max=2400.0)
    b = refine_skew_walls(_walls(), scene, z_min=500.0, z_max=2400.0, index=idx)
    assert _axes(a) == _axes(b)


def test_the_rotation_actually_moves_something(scene):
    """Mutaatiosuoja: jos kierto ei tee mitään, identtisyys olisi tyhjä väite."""
    before = _walls()
    after = fine_rotate_walls(before, scene, z_min=500.0, z_max=2400.0)
    assert _axes(before) != _axes(after)


class _FakeCloud:
    def __init__(self, pts):
        self.points = pts


def test_the_same_cloud_is_indexed_once(scene):
    clear_index_cache()
    c = _FakeCloud(scene)
    first = index_for(c, scene)
    assert index_for(c, scene) is first
    assert index_for(_FakeCloud(scene), scene) is not first
    clear_index_cache()
    assert index_for(c, scene) is not first


def test_a_resized_cloud_is_reindexed(scene):
    """Paikallaan muokattu pilvi ei saa saada vanhaa indeksiä."""
    clear_index_cache()
    c = _FakeCloud(scene)
    first = index_for(c, scene)
    assert index_for(c, scene[:-10]) is not first
    clear_index_cache()


# --- Kierros 2: aukot, katkaisu, kate, lunastus ------------------------------

def _holed_face(a, b, hole=(5000.0, 6500.0), z_hole=(0.0, 2100.0), step=12.0):
    """Pystypinta jossa on ovikokoinen reikä."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    t = np.arange(0.0, L, step)
    zs = np.arange(60.0, _H - 60.0, step)
    S, Z = np.meshgrid(t, zs, indexing="ij")
    keep = ~((S >= hole[0]) & (S <= hole[1]) & (Z >= z_hole[0]) & (Z <= z_hole[1]))
    u = (b - a) / L
    xy = a + u * S[keep][:, None]
    return np.column_stack([xy, Z[keep]])


@pytest.fixture(scope="module")
def holed():
    pts = np.vstack([_holed_face((0.0, 0.0), (14000.0, 0.0)),
                     _holed_face((0.0, 200.0), (14000.0, 200.0)),
                     _face((0.0, 0.0), (0.0, 9000.0)),
                     _face((200.0, 0.0), (200.0, 9000.0))])
    assert len(pts) > 300_000, len(pts)
    return pts


def test_openings_are_bit_identical_with_an_index(holed):
    from ordinate.core.segmentation.opening_detector import _wall_openings

    w = _wall("seina", (0.0, 100.0), (14000.0, 100.0))
    walls = [w, _wall("pysty", (100.0, 0.0), (100.0, 9000.0))]
    a = _wall_openings(w, holed, 0.0, 0, walls)
    b = _wall_openings(w, holed, 0.0, 0, walls, XYIndex(holed, 20.0))
    assert a, "reikä pitää löytyä, muuten identtisyys on tyhjä väite"
    assert [o.model_dump() for o in a] == [o.model_dump() for o in b]


def test_split_at_gaps_is_bit_identical_with_an_index(holed):
    from ordinate.core.semantics.split_gaps import split_walls_at_gaps

    pts = np.vstack([holed, _face((20000.0, 0.0), (28000.0, 0.0))])
    walls = [_wall("pitka", (0.0, 100.0), (28000.0, 100.0))]
    a = split_walls_at_gaps(walls, pts)
    b = split_walls_at_gaps(walls, pts, XYIndex(pts, 20.0))
    assert len(a) > 1, "seinän pitää katketa aukosta"
    assert _axes(a) == _axes(b)
    assert [w.id for w in a] == [w.id for w in b]


def test_overstretch_coverage_is_bit_identical_with_an_index(holed):
    from ordinate.core.semantics.overstretch import _coverage

    xy = holed[:, :2]
    w = _wall("seina", (0.0, 100.0), (14000.0, 100.0))
    ca, La, aa, ba = _coverage(w, xy)
    cb, Lb, ab, bb = _coverage(w, xy, XYIndex(xy, 20.0))
    assert ca.any(), "katteen pitää löytyä"
    assert np.array_equal(ca, cb) and La == Lb


def test_claimed_matches_the_plain_scan(holed):
    """Indeksoitu lunastus vs. suora koko taulukon skannaus."""
    from ordinate.core.semantics.residual_walls import (
        _CLAIM_BAND, _CLAIM_END, _claimed,
    )

    # Kaukainen pinta jota mikään seinä ei lunasta → tulos on osittainen.
    band = np.vstack([holed, _face((40000.0, 40000.0), (48000.0, 40000.0))])
    walls = [_wall("a", (0.0, 100.0), (14000.0, 100.0)),
             _wall("b", (100.0, 0.0), (100.0, 9000.0)),
             _wall("c", (0.0, 100.0), (300.0, 100.0))]
    got = _claimed(band, walls)
    xy = band[:, :2]
    ref = np.zeros(len(band), dtype=bool)
    for w in walls:
        a = np.asarray(w.axis[0], float)
        b = np.asarray(w.axis[1], float)
        L = float(np.linalg.norm(b - a))
        if L < 500.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        ref |= ((s > -_CLAIM_END) & (s < L + _CLAIM_END)
                & (np.abs(t) < w.thickness / 2.0 + _CLAIM_BAND))
    assert ref.any() and not ref.all(), "lunastuksen pitää olla osittainen"
    assert np.array_equal(got, ref)


def test_split_uses_the_whole_cloud_for_the_thin_band_rule(holed):
    """`band`-varasääntö lasketaan KOKO pilvestä, ei kaistalta.

    Sääntö on: alle 50 pistettä seinän z-kaistalla → käytä koko pilveä
    z-suodatuksen sijaan. Jos luku laskettaisiin kaistaindeksin osajoukosta,
    ehto lauteaisi eri hetkellä ja seinä katkeaisi eri kohdasta. Tässä
    seinän omat pisteet ovat z-kaistan ULKOPUOLELLA ja kaukana on möykky
    sen SISÄLLÄ → koko pilvi ylittää 50:n, kaista ei.
    """
    from ordinate.core.semantics.split_gaps import split_walls_at_gaps

    def _low_face(a, b):
        pts = _face(a, b)
        return pts[(pts[:, 2] < 600.0) | (pts[:, 2] > 2100.0)]

    rng = np.random.default_rng(3)
    far = np.column_stack([
        rng.uniform(40000.0, 41000.0, 4000),
        rng.uniform(40000.0, 41000.0, 4000),
        rng.uniform(900.0, 1800.0, 4000),
    ])
    pts = np.vstack([_low_face((0.0, 0.0), (9000.0, 0.0)),
                     _low_face((0.0, 200.0), (9000.0, 200.0)),
                     _low_face((20000.0, 0.0), (28000.0, 0.0)),
                     _low_face((20000.0, 200.0), (28000.0, 200.0)),
                     far])
    from ordinate.core.semantics.split_gaps import _split_one

    w = _wall("pitka", (0.0, 100.0), (28000.0, 100.0))
    index = XYIndex(pts, 20.0)
    a = split_walls_at_gaps([w], pts)
    b = split_walls_at_gaps([w], pts, index)
    assert _axes(a) == _axes(b)
    # Ja sääntö tekee oikeasti työtä: jos luku laskettaisiin kaistalta
    # (z_sorted=None), seinä katkeaisi — eli tulos olisi eri.
    naive = _split_one(w, pts, index, None)
    assert len(naive) > len(a), "varasäännön pitää muuttaa tulosta"


def test_openings_pick_the_face_from_the_whole_plane_strip():
    """Pinnanvalintaa EI saa laskea akselin suunnassa rajatusta joukosta.

    `_wall_openings` valitsee mitattavan pinnan sen mukaan kummalla puolella on
    enemmän pisteitä KOKO tasokaistalla — myös seinän päiden ulkopuolelta.
    Siksi kaistahaku saa rajata vain kohtisuoraan. Tässä seinän kohdalla
    voittaa toinen pinta ja koko kaistalla toinen: jos rajaus tehtäisiin,
    aukot luettaisiin väärältä pinnalta.
    """
    from ordinate.core.segmentation.opening_detector import _FACE_TOL, _wall_openings

    L = 14000.0
    near = _holed_face((0.0, 0.0), (L, 0.0))            # tiheä, reikä
    far = _face((0.0, 200.0), (L, 200.0), step=40.0)    # harva, ehjä
    beyond = _face((L, 200.0), (40000.0, 200.0))        # seinän ULKOPUOLELLA
    pts = np.vstack([near, far, beyond])

    d = pts[:, 1] - 100.0
    in_range = (pts[:, 0] >= 0.0) & (pts[:, 0] <= L)
    pos_all = int((np.abs(d - 100.0) < _FACE_TOL).sum())
    neg_all = int((np.abs(d + 100.0) < _FACE_TOL).sum())
    pos_in = int((np.abs(d - 100.0) < _FACE_TOL)[in_range].sum())
    neg_in = int((np.abs(d + 100.0) < _FACE_TOL)[in_range].sum())
    assert pos_all > neg_all and neg_in > pos_in, "koeasetelma ei erottele"

    w = _wall("seina", (0.0, 100.0), (L, 100.0))
    a = _wall_openings(w, pts, 0.0, 0, [w])
    b = _wall_openings(w, pts, 0.0, 0, [w], XYIndex(pts, 20.0))
    assert [o.model_dump() for o in a] == [o.model_dump() for o in b]


# --- Kierros 3: toimituspaksuus ja pistevälin KD-puu -------------------------

class _Cloud:
    def __init__(self, pts):
        self.points = pts


def _lopsided_wall_cloud():
    """Seinä jonka pintojen tiheys on EPÄSYMMETRINEN sekä puolittain että
    pituussuunnassa: alkupäässä on enemmän pisteitä +puolella, loppupäässä
    selvästi enemmän −puolella. Koko seinältä luettuna − voittaa, mutta
    pelkästä alkupuoliskosta + voittaisi.

    Ilman tällaista epäsymmetriaa akselin ankkurointi antaa saman vastauksen
    väärälläkin kaistalla, eikä testi todista mitään.
    """
    return np.vstack([
        _face((0.0, 200.0), (7000.0, 200.0), step=12.0),
        _face((0.0, 0.0), (7000.0, 0.0), step=40.0),
        _face((7000.0, 0.0), (14000.0, 0.0), step=8.0),
        _face((7000.0, 200.0), (14000.0, 200.0), step=90.0),
    ])


def test_delivery_thickness_snap_is_bit_identical_with_an_index():
    """Akselin ankkurointi dominanttiin pintaan ei saa muuttua indeksoinnista."""
    from ordinate.core.pipeline import _snap_delivery_thickness, _xy_index

    pts = _lopsided_wall_cloud()
    assert len(pts) > 300_000, len(pts)
    # Mitattu paksuus 197 mm → snap 200 mm → akseli siirtyy 1.5 mm.
    walls = [_wall(f"w{i}", (0.0, 100.0), (14000.0, 100.0), thickness=197.0)
             for i in range(3)]
    c = _Cloud(pts)
    assert _xy_index(pts, walls, c) is not None, "indeksin pitää syntyä"
    got = _snap_delivery_thickness(walls, c)
    assert [w.thickness for w in got] == [200.0] * 3, "snapin pitää tapahtua"
    assert _axes(got) != _axes(walls), "akselin pitää siirtyä"

    # Viite: sama algoritmi koko pistetaulukolla, ilman kaistahakua.
    ref = []
    for w in walls:
        p0 = np.array(w.axis[0], float)
        p1 = np.array(w.axis[1], float)
        L = float(np.linalg.norm(p1 - p0))
        u = (p1 - p0) / L
        n = np.array([-u[1], u[0]])
        rel = pts[:, :2] - p0
        t, perp = rel @ u, rel @ n
        zm = (pts[:, 2] > w.z_min + 200.0) & (pts[:, 2] < w.z_min + w.height - 200.0)
        band = zm & (t > 0) & (t < L) & (np.abs(perp) < w.thickness / 2.0 + 60.0)
        side_pos = int((perp[band] > 0).sum())
        face_sign = 1.0 if side_pos >= int(band.sum()) - side_pos else -1.0
        sh = -face_sign * ((200.0 - w.thickness) / 2.0) * n
        ref.append(((round(p0[0] + sh[0], 2), round(p0[1] + sh[1], 2)),
                    (round(p1[0] + sh[0], 2), round(p1[1] + sh[1], 2))))
    assert _axes(got) == ref


def test_nn_spacing_is_unchanged_by_the_faster_tree():
    """Nopea puunrakennus ei muuta etäisyyksiä — vain rakennusaikaa."""
    from scipy.spatial import cKDTree

    from ordinate.core.geometry.loader import _nn_spacing

    rng = np.random.default_rng(11)
    xyz = rng.normal(0.0, 5000.0, (200_000, 3))
    n = min(len(xyz), 20_000)
    idx = np.linspace(0, len(xyz) - 1, n).astype(np.int64)
    ref, _ = cKDTree(xyz).query(xyz[idx], k=2)
    ref = ref[:, 1]
    ref = ref[ref > 0.0]
    assert _nn_spacing(xyz) == float(np.median(ref))

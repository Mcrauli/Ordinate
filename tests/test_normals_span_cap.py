"""Matala väliseinä korkeassa hallissa on seinä siinä missä muutkin.

`wall_normals` vaati segmentiltä 45 % kaistan korkeudesta. 10 m runkohallissa
se on 4.05 m, joten 2–4 m väliseinä oli mahdoton riippumatta siitä onko se
oikea seinä — sama taso-eikä-suhde-vika kuin `wall_histogram`in entisessä
globaalissa piikkikynnyksessä. Mitattu GT:llä viidellä Rohbau-scenellä:
kattavuus 0.316 → 0.768 ja tarkkuus 0.725 → 0.846.
"""
import numpy as np
import open3d as o3d
import pytest

from scan2bim.core.segmentation import wall_normals as WN

_STEP = 60.0


def _plane_yz(x, y0, y1, z0, z1):
    y = np.arange(y0, y1, _STEP)
    z = np.arange(z0, z1, _STEP)
    yy, zz = np.meshgrid(y, z)
    return np.column_stack([np.full(yy.size, x), yy.ravel(), zz.ravel()])


def _plane_xz(y, x0, x1, z0, z1):
    p = _plane_yz(y, x0, x1, z0, z1)
    return p[:, [1, 0, 2]]


def _plane_xy(z, x0, x1, y0, y1):
    x = np.arange(x0, x1, _STEP * 3)
    y = np.arange(y0, y1, _STEP * 3)
    xx, yy = np.meshgrid(x, y)
    return np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)])


def _tall_hall(inner_top=3500.0):
    """8 x 6 m halli jonka vapaa korkeus on 9 m, ja sen sisällä matala seinä.

    Kaista on floor+400 .. ceiling-300 eli noin 8.3 m, joten vanha sääntö
    vaatii 3.7 m. Väliseinä yltää kaistan sisällä 3.1 m — selvästi alle vanhan
    vaatimuksen ja selvästi yli uuden 2.4 m katkaisun, joten koeasetelma
    erottelee säännöt eikä ole rajatapaus kumpaankaan suuntaan.
    """
    parts = []
    for x in (0.0, 200.0, 7800.0, 8000.0):
        parts.append(_plane_yz(x, 0.0, 6000.0, 0.0, 9000.0))
    for y in (0.0, 200.0, 5800.0, 6000.0):
        parts.append(_plane_xz(y, 0.0, 8000.0, 0.0, 9000.0))
    for x in (3900.0, 4100.0):          # matala väliseinä, 4 m pitkä
        parts.append(_plane_yz(x, 1000.0, 5000.0, 0.0, inner_top))
    parts.append(_plane_xy(0.0, 0.0, 8000.0, 0.0, 6000.0))
    parts.append(_plane_xy(9000.0, 0.0, 8000.0, 0.0, 6000.0))
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pc


def _has_inner_wall(walls):
    """Onko mallissa seinä joka kulkee x ≈ 4000 pitkin y-akselia?"""
    for w in walls:
        a = np.asarray(w.axis[0], float)
        b = np.asarray(w.axis[1], float)
        if abs(a[0] - 4000.0) < 250.0 and abs(b[0] - 4000.0) < 250.0 \
                and abs(b[1] - a[1]) > 2000.0:
            return True
    return False


@pytest.fixture(scope="module")
def hall():
    return _tall_hall()


def test_a_low_partition_in_a_tall_hall_is_found(hall):
    assert _has_inner_wall(WN.NormalsWallDetector().detect(hall).walls)


def test_the_old_rule_would_have_missed_it(hall, monkeypatch):
    """Mutaatiosuoja: ilman katkaisua koeasetelman on oikeasti kaaduttava."""
    monkeypatch.setattr(WN, "_SPAN_CAP", 1e9)
    assert not _has_inner_wall(WN.NormalsWallDetector().detect(hall).walls)


def test_the_perimeter_survives_either_way(hall):
    """Katkaisu ei saa maksaa mitään: pitkät seinät löytyvät yhä."""
    walls = WN.NormalsWallDetector().detect(hall).walls
    assert len(walls) >= 4, f"perimetri katosi: {len(walls)} seinää"


def test_a_knee_high_ledge_is_still_rejected(hall):
    """Portti tekee yhä työnsä: 0.8 m korkea pinta ei ole seinä.

    Ilman tätä katkaisu olisi voinut vain poistaa portin — mitattuna ilman
    porttia tarkkuus romahtaa 0.725 → 0.318.
    """
    walls = WN.NormalsWallDetector().detect(_tall_hall(inner_top=800.0)).walls
    assert not _has_inner_wall(walls)


def test_a_low_room_keeps_the_old_rule_exactly():
    """Katkaisu ei saa purra tavallisessa rakennuksessa.

    Kellarin kaista on noin 1075 mm, jolloin vanha vaatimus on 484 mm — reilusti
    alle katkaisun, joten sääntö on siellä bitilleen entinen.

    Korkeudet ovat kellarin OMASSA koordinaatistossa (z ≈ 7.1 m), koska
    ratkaisevaa on kaistan korkeus eikä etäisyys origosta. Nollasta mitattuna
    tämä testi ei erottaisi `z_hi - z_lo`:ta `z_hi`:stä lainkaan.
    """
    z_lo, z_hi = 7519.3, 8594.7
    assert WN._need_span(z_lo, z_hi) == pytest.approx(WN._SPAN_FRAC * (z_hi - z_lo))
    assert WN._need_span(z_lo, z_hi) < WN._SPAN_CAP


def test_the_cap_binds_only_above_six_and_a_half_metres():
    edge = WN._SPAN_CAP / WN._SPAN_FRAC
    assert WN._need_span(0.0, edge - 1.0) < WN._SPAN_CAP
    assert WN._need_span(0.0, edge + 1.0) == pytest.approx(WN._SPAN_CAP)


@pytest.mark.parametrize("band", [500.0, 1075.0, 2000.0, 5333.0, 8300.0, 20000.0])
def test_the_rule_is_never_stricter_than_before(band):
    assert WN._need_span(0.0, band) <= WN._SPAN_FRAC * band + 1e-9

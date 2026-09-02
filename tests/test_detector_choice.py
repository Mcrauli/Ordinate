"""Detektorivalinta ei saa palkita MÄÄRÄSTÄ.

`wall_coverage` on puhdas recall: jokainen lisätty seinä voi vain nostaa sitä,
eikä yksikään väärä laske sitä. Mitattu seuraus: kun histogrammidetektorin
piikkikynnystä löysättiin, se voitti kellarin valintakisan kattavuudella 0.103
ja vei lopputuloksen 0.366 → 0.203 (240 → 123 seinää), retail_l:n 37 → 10.
"""
import numpy as np
import pytest

from scan2bim.core.qa.coverage import wall_coverage, wall_scores
from scan2bim.schemas.model import ElementSource, Wall

_H = 2700.0


def _wall(wid, a, b, thickness=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="normals"),
                axis=[list(a), list(b)], height=_H, thickness=thickness, z_min=0.0)


def _face(a, b, step=25.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    L = float(np.linalg.norm(b - a))
    t = np.arange(0.0, L, step) / L
    xy = a + (b - a) * t[:, None]
    zs = np.arange(60.0, _H - 60.0, step)
    out = np.repeat(xy, len(zs), axis=0)
    return np.column_stack([out, np.tile(zs, len(xy))])


@pytest.fixture(scope="module")
def scene():
    """Yksi aito seinä: pinnat y=0 ja y=200, akseli y=100."""
    return np.vstack([_face((0.0, 0.0), (12000.0, 0.0)),
                      _face((0.0, 200.0), (12000.0, 200.0)),
                      _clutter()])


def _real(): return [_wall("oikea", (0.0, 100.0), (12000.0, 100.0))]


def _clutter():
    """Matalaa roinaa: pystyä pintaa mutta ei kaistan korkuista → ei seinämäistä.

    Valeseinä TYHJÄSSÄ tilassa ei lunasta yhtään pistettä eikä siis laske
    tarkkuutta — se on näkymätön molemmille mittareille. Detektorin ylimääräiset
    piikit eivät kuitenkaan synny tyhjästä vaan roinasta (putket, hyllyt,
    työmaatavara), joten juuri se on mitattava tapaus.
    """
    out = []
    for i in range(10):
        y = 2000.0 + 900.0 * i
        f = _face((0.0, y), (12000.0, y))
        out.append(f[f[:, 2] < 700.0])          # vain alaosa → ei täytä kaistaa
    return np.vstack(out)


def _flood():
    """Sama oikea seinä + kymmenen valeseinää roinan päällä."""
    return _real() + [_wall(f"vale{i}", (0.0, 2000.0 + 900.0 * i),
                            (12000.0, 2000.0 + 900.0 * i), thickness=1.0)
                      for i in range(10)]


def test_coverage_alone_cannot_tell_them_apart(scene):
    """Juuri tämä on vika: tulva ei laske kattavuutta lainkaan."""
    a = wall_coverage(scene, _real(), 0.0, _H)
    b = wall_coverage(scene, _flood(), 0.0, _H)
    assert a > 0.0
    assert b >= a, "valeseinät eivät voi laskea recallia"


def test_precision_punishes_the_flood(scene):
    cov_a, pre_a = wall_scores(scene, _real(), 0.0, _H)
    cov_b, pre_b = wall_scores(scene, _flood(), 0.0, _H)
    assert pre_b < pre_a, "tarkkuuden on romahdettava tulvasta"


def test_f1_prefers_the_honest_model(scene):
    def f1(walls):
        c, p = wall_scores(scene, walls, 0.0, _H)
        return 0.0 if c + p <= 0.0 else 2.0 * c * p / (c + p)
    assert f1(_real()) > f1(_flood())


def test_coverage_still_returns_the_same_number(scene):
    """`wall_coverage` on yhä sama arvo — muut kutsujat eivät muutu."""
    for walls in (_real(), _flood()):
        assert wall_coverage(scene, walls, 0.0, _H) == wall_scores(
            scene, walls, 0.0, _H)[0]


def test_an_empty_model_scores_zero(scene):
    assert wall_scores(scene, [], 0.0, _H) == (0.0, 0.0)


def test_detector_score_is_the_harmonic_mean():
    from scan2bim.core.qa.coverage import detector_score

    assert detector_score(0.0, 0.0) == 0.0
    assert detector_score(1.0, 1.0) == 1.0
    # Epätasapaino rankaisee: 0.9/0.1 on huonompi kuin 0.5/0.5.
    assert detector_score(0.9, 0.1) < detector_score(0.5, 0.5)
    # Ja pelkkä kattavuus EI erottaisi näitä kahta.
    assert detector_score(0.9, 0.1) < detector_score(0.9, 0.8)

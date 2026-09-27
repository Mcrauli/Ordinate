"""_dense_segment / coverage-confidence: iso liiketila-skene aliarvioi sisäseinät
koko-suhteisella confidencella (12 m takahuoneseinä = murto-osa koko pilvestä →
conf ~0.01 → pudotettiin). Skaalariippumaton peitto pelastaa aidon seinän."""
import numpy as np

from ordinate.core.segmentation.wall_ransac import _dense_segment


def _proj_uniform(lo, hi, n=5000, seed=0):
    return np.random.RandomState(seed).uniform(lo, hi, n)


def test_solid_wall_high_coverage():
    # yhtäjaksoinen 12 m seinä → peitto ~1.0
    cov, t0, t1 = _dense_segment(_proj_uniform(0, 12000))
    assert cov > 0.9, f"aito seinä sai matalan peiton {cov:.2f}"


def test_column_line_low_coverage():
    # 3 pilaria 8 m välein (kukin ~0.4 m) → ei yhtäjaksoista seinää → matala peitto
    cols = np.concatenate([
        np.random.RandomState(i).uniform(c - 200, c + 200, 300)
        for i, c in enumerate((0.0, 8000.0, 16000.0))
    ])
    cov, _, _ = _dense_segment(cols)
    assert cov < 0.5, f"pilaririvi sai seinätasoisen peiton {cov:.2f}"


def test_contaminated_tail_measures_dense_run():
    # 12 m tiheä seinä + harva 8 m häntä (pilarikontaminaatio) → peitto mitataan
    # tiheästä jänteestä, ei koko 20 m välistä
    dense = _proj_uniform(0, 12000, n=6000)
    tail = _proj_uniform(12000, 20000, n=120)  # harva
    cov, t0, t1 = _dense_segment(np.concatenate([dense, tail]))
    assert cov > 0.85, f"kontaminoitu seinä sai matalan peiton {cov:.2f}"


def test_door_gap_bridged():
    # seinä 0..5 m ja 6..11 m (1 m ovi keskellä) → sillataan → yksi seinä, korkea peitto
    w = np.concatenate([_proj_uniform(0, 5000, 3000), _proj_uniform(6000, 11000, 3000)])
    cov, _, _ = _dense_segment(w)
    assert cov > 0.9, f"ovi-aukko katkaisi seinän, peitto {cov:.2f}"

"""_looks_like_retail: semantic_filter_mode="auto" kytkee PointNet-suodattimen
vain big-box-liiketilaan (iso pohja + korkea tila). Asuintila/rohbau (matala) ei
saa triggeröidä — suodatin regressoi niitä (talo 9→8 seinää, 2→1 huone)."""
import numpy as np

from scan2bim.core.pipeline import _looks_like_retail


class _Cloud:
    def __init__(self, pts):
        self.points = pts


def _box(nx, ny, height_mm, span_x_mm, span_y_mm, seed=0):
    rng = np.random.RandomState(seed)
    n = 50_000
    return _Cloud(np.column_stack([
        rng.uniform(0, span_x_mm, n),
        rng.uniform(0, span_y_mm, n),
        rng.uniform(0, height_mm, n),
    ]))


def test_retail_big_box_detected():
    # 60x40 m, 7 m korkea = liiketila
    assert _looks_like_retail(_box(0, 0, 7000, 60_000, 40_000)) is True


def test_apartment_not_retail():
    # ~7x4 m, 2.7 m = asunto
    assert _looks_like_retail(_box(0, 0, 2700, 7000, 4000)) is False


def test_large_but_low_not_retail():
    # iso pohja mutta matala (avokonttori/rohbau-kerros) → ei triggeröi
    assert _looks_like_retail(_box(0, 0, 3000, 60_000, 40_000)) is False


def test_tall_but_small_not_retail():
    # korkea mutta pieni (porras/kuilu) → ei triggeröi
    assert _looks_like_retail(_box(0, 0, 7000, 3000, 3000)) is False


def test_empty_cloud_not_retail():
    assert _looks_like_retail(_Cloud(np.zeros((10, 3)))) is False

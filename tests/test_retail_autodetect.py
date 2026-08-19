"""_looks_like_retail: semantic_filter_mode="auto" kytkee PointNet-suodattimen
vain big-box-liiketilaan (iso pohja + korkea tila). Asuintila/rohbau (matala) ei
saa triggeröidä — suodatin regressoi niitä (talo 9→8 seinää, 2→1 huone)."""
import numpy as np

from scan2bim.core.pipeline import _looks_like_retail


class _Cloud:
    def __init__(self, pts):
        self.points = pts


def _box(nx, ny, height_mm, span_x_mm, span_y_mm, seed=0, n=50_000):
    rng = np.random.RandomState(seed)
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


def _thin(cloud, k):
    return _Cloud(cloud.points[::k])


def test_decision_does_not_change_with_point_density():
    """Sama tila harvennettuna: paatoksen on pysyttava samana.

    Percentiiliala on tiheyspainotettu — skannerin ymparilla oleva tihea alue
    kutistaa sen. Mitattu Rohbau scene_07004, sama pilvi harvennettuna:
    588 -> 1002 -> 1112 -> 1142 -> 1162 -> 1172 m2, eli paatos vaihtui rajan
    600 yli PELKASTA harventamisesta. Miehitysala samalla sarjalla 802 -> 783.
    """
    # Pistemaara riittava jotta harvinkin sarja pysyy realistisella
    # tiheydella: alle 3 pistetta nelioametrilla ei ole enaa rakennusskanni,
    # ja `scan2bim inspect` varoittaa siita erikseen.
    big = _box(0, 0, 7000, 60_000, 40_000, n=800_000)
    small = _box(0, 0, 2700, 7000, 4000, n=800_000)
    for k in (1, 2, 4, 8, 16):
        assert _looks_like_retail(_thin(big, k)) is True, f"iso tila, harvennus 1/{k}"
        assert _looks_like_retail(_thin(small, k)) is False, f"asunto, harvennus 1/{k}"


def test_a_scanner_room_does_not_shrink_the_footprint():
    """Puolet pisteista yhdessa nurkassa: percentiiliala kutistuu, miehitysala ei.

    Tama on juuri se tilanne joka tuotti tiheysriippuvuuden — asemat seisovat
    yhdessa osassa rakennusta ja tihea alue dominoi percentiilia.
    """
    rng = np.random.RandomState(4)
    wide = np.column_stack([rng.uniform(0, 60_000, 50_000),
                            rng.uniform(0, 40_000, 50_000),
                            rng.uniform(0, 7000, 50_000)])
    corner = np.column_stack([rng.uniform(0, 6_000, 3_000_000),
                              rng.uniform(0, 4_000, 3_000_000),
                              rng.uniform(0, 7000, 3_000_000)])
    pts = np.vstack([wide, corner])
    dx = float(np.percentile(pts[:, 0], 99) - np.percentile(pts[:, 0], 1))
    dy = float(np.percentile(pts[:, 1], 99) - np.percentile(pts[:, 1], 1))
    assert (dx * dy) / 1e6 < 600.0, "fikstuuri ei kutista percentiilialaa"
    assert _looks_like_retail(_Cloud(pts)) is True

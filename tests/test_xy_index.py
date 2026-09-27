"""XYIndex: haun on palautettava YLIJOUKKO kaistasta, nousevassa jarjestyksessa.

Jos indeksi pudottaisi yhdenkin kaistan pisteen, seinan sijainti muuttuisi
hiljaa. Jos jarjestys muuttuisi, percentiilit ja mediaanit voisivat muuttua.
Nama testit vertaavat suoraan tayteen skannaukseen.
"""
import numpy as np

from ordinate.core.geometry.xy_index import XYIndex


def _cloud(n=60000, seed=7):
    rng = np.random.RandomState(seed)
    return np.column_stack([rng.uniform(-40000, 40000, n),
                            rng.uniform(-25000, 25000, n),
                            rng.uniform(0, 7000, n)])


def _brute(pts, p0, along, normal, radius, s_lo=-np.inf, s_hi=np.inf):
    rel = pts[:, :2] - p0
    d = np.abs(rel @ normal)
    s = rel @ along
    return np.where((d <= radius) & (s >= s_lo) & (s <= s_hi))[0]


def test_superset_and_sorted_for_many_orientations():
    pts = _cloud()
    idx_all = XYIndex(pts)
    rng = np.random.RandomState(1)
    for _ in range(25):
        ang = rng.uniform(0, np.pi)
        along = np.array([np.cos(ang), np.sin(ang)])
        normal = np.array([-along[1], along[0]])
        p0 = np.array([rng.uniform(-30000, 30000), rng.uniform(-20000, 20000)])
        radius = rng.choice([30.0, 200.0, 600.0])
        s_lo, s_hi = [(-np.inf, np.inf), (0.0, 12000.0),
                      (-400.0, 8000.0)][rng.randint(3)]
        got = idx_all.near_segment(p0, along, normal, radius, s_lo, s_hi)
        want = _brute(pts, p0, along, normal, radius, s_lo, s_hi)
        assert np.all(np.diff(got) > 0), "indeksit eivat nousevassa jarjestyksessa"
        assert np.isin(want, got).all(), "kaistan pisteita puuttuu ylijoukosta"


def test_predicate_reapplied_gives_identical_selection():
    """Kutsuja soveltaa saman ehdon ylijoukkoon -> tasmalleen sama pistejoukko."""
    pts = _cloud()
    idx_all = XYIndex(pts)
    along = np.array([1.0, 0.0])
    normal = np.array([0.0, 1.0])
    p0 = np.array([-5000.0, 1234.0])
    radius = 200.0
    cand = idx_all.near_segment(p0, along, normal, radius)
    sub = pts[cand]
    keep = np.abs((sub[:, :2] - p0) @ normal) <= radius
    got = cand[keep]
    want = _brute(pts, p0, along, normal, radius)
    np.testing.assert_array_equal(got, want)


def test_empty_cloud_and_empty_result():
    assert len(XYIndex(np.zeros((0, 3))).near_segment(
        np.zeros(2), np.array([1.0, 0.0]), np.array([0.0, 1.0]), 100.0)) == 0
    pts = _cloud(1000)
    far = XYIndex(pts).near_segment(np.array([1e7, 1e7]), np.array([1.0, 0.0]),
                                    np.array([0.0, 1.0]), 10.0)
    assert len(far) == 0

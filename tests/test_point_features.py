"""point_features.geometric: lohkotuksen on annettava TASMALLEEN sama tulos.

Lohkotus tehtiin muistin takia (naapurihaun N*k*3 float64 kahdesti = ~6 GB
8 M pisteella = koko putken muistipiikki isolla liiketilaskannilla). Jos
lohkotus muuttaisi arvoja, semanttinen suodatin muuttuisi eika mitattuja
tuloksia voisi verrata vanhoihin.
"""
import numpy as np

from scan2bim.core.segmentation import point_features as pf


def _scene(n=4000, seed=1):
    rng = np.random.RandomState(seed)
    wall = np.column_stack([rng.normal(0, 3, n), rng.uniform(0, 5000, n),
                            rng.uniform(0, 2700, n)])
    floor = np.column_stack([rng.uniform(0, 4000, n), rng.uniform(0, 5000, n),
                             rng.normal(0, 3, n)])
    blob = rng.uniform(1000, 1600, (n, 3))
    return np.vstack([wall, floor, blob])


def test_chunking_is_exact():
    pts = _scene()
    ref = pf.geometric(pts, chunk=len(pts) + 1)
    for c in (137, 1000, 5000):
        np.testing.assert_array_equal(pf.geometric(pts, chunk=c), ref)


def test_verticality_separates_wall_from_floor():
    n = 4000
    pts = _scene(n)
    g = pf.geometric(pts)
    assert g[:n, 0].mean() > g[n:2 * n, 0].mean(), "pystypinta ei erotu lattiasta"
    assert g[:n, 1].mean() > g[2 * n:, 1].mean(), "taso ei erotu mossosta"

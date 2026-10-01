"""wall_verifier: puiden läpikäynti ja pilvestä lasketut piirteet."""
import numpy as np

from ordinate.core.semantics import wall_verifier as V


def _tree(feature, threshold, lo, hi):
    return {"left": np.array([1, -1, -1]), "right": np.array([2, -1, -1]),
            "feature": np.array([feature, 0, 0]), "threshold": np.array([threshold, 0.0, 0.0]),
            "value": np.array([0.0, lo, hi])}


def test_predict_follows_split():
    X = np.zeros((2, len(V.FEATURES)))
    k = V.FEATURES.index("horiz_hi")
    X[0, k], X[1, k] = 0.1, 0.9
    p = V.predict([_tree(k, 0.5, 0.9, 0.1)], X)
    assert p[0] == 0.9 and p[1] == 0.1


def test_predict_averages_trees():
    X = np.zeros((1, len(V.FEATURES)))
    p = V.predict([_tree(0, 1.0, 1.0, 0.0), _tree(0, 1.0, 0.0, 0.0)], X)
    assert p[0] == 0.5


def _wall(x0, y0, x1, y1, t=200.0):
    return {"axis": [[x0, y0], [x1, y1]], "thickness": t}


def _plane(x0, x1, y, z0, z1, step=20.0):
    xs, zs = np.meshgrid(np.arange(x0, x1, step), np.arange(z0, z1, step))
    return np.column_stack([xs.ravel(), np.full(xs.size, y), zs.ravel()])


def test_full_height_wall_reads_as_wall():
    q = _plane(0, 4000, 100.0, 0, 2700)
    nz = np.zeros(len(q))
    X, _ = V.features([_wall(0, 0, 4000, 0)], [], q, nz, 0.0, 2700.0, [0])
    f = dict(zip(V.FEATURES, X[0]))
    assert f["horiz"] == 0.0 and f["cont_mid"] > 0.9
    assert all(f[f"vp{i}"] > 0.05 for i in range(V.NB))


def test_beam_line_is_top_heavy_and_horizontal():
    xs, ys = np.meshgrid(np.arange(0, 4000, 20.0), np.arange(-100, 300, 20.0))
    q = np.column_stack([xs.ravel(), ys.ravel(), np.full(xs.size, 2400.0)])
    nz = np.ones(len(q))
    X, _ = V.features([_wall(0, 0, 4000, 0)], [], q, nz, 0.0, 2700.0, [0])
    f = dict(zip(V.FEATURES, X[0]))
    assert f["horiz_hi"] == 1.0 and f["cont_mid"] == 0.0


def test_crossing_counts_x_not_t():
    a = _wall(0, 0, 4000, 0)
    x = _wall(2000, -2000, 2000, 2000)
    t = _wall(2000, 0, 2000, 2000)
    assert V._topo(a, [x])[0] == 1.0
    assert V._topo(a, [t])[0] == 0.0


def test_shipped_model_matches_feature_list():
    trees = V.load()
    assert trees is not None and len(trees) > 0

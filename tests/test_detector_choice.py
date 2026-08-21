"""Detektorin valinta mitataan, ei paateta rakennuksen koosta.

Aiemmin iso pohja-ala reititti aina histogrammille, joka on rakennettu
suorakulmaiseen avoimeen liiketilaan. Koulun kellari on iso mutta sokkeloinen
ja matala: mitattu kattavuus 0.009 histogrammilla ja 0.045 contourilla.
"""
import numpy as np
import pytest

import scan2bim.core.segmentation.wall_contour    # noqa: F401 — rekisteroi detektorit
import scan2bim.core.segmentation.wall_density    # noqa: F401
import scan2bim.core.segmentation.wall_histogram  # noqa: F401
import scan2bim.core.segmentation.wall_ransac     # noqa: F401
from scan2bim.core.pipeline import Pipeline, PipelineConfig
from scan2bim.core.qa.coverage import wall_coverage
from scan2bim.schemas.model import ElementSource, Wall


def _cloud(pts):
    o3d = pytest.importorskip("open3d")
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return pc


def _room(size=6000.0, height=2600.0, step=30.0):
    """Neljä seinää, lattia ja katto — pisteet pinnoilla."""
    xs = np.arange(0.0, size, step)
    zs = np.arange(0.0, height, step)
    walls = []
    for c in (0.0, size):
        gx, gz = np.meshgrid(xs, zs)
        walls.append(np.column_stack([gx.ravel(), np.full(gx.size, c), gz.ravel()]))
        walls.append(np.column_stack([np.full(gx.size, c), gx.ravel(), gz.ravel()]))
    gx, gy = np.meshgrid(xs, xs)
    flat = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])
    ceil = np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, height)])
    return np.vstack([*walls, flat, ceil])


def test_coverage_is_zero_when_the_model_has_no_walls():
    """Tyhja malli ei saa nayttaa taydelta kattavuudelta — muuten se voittaisi
    valinnan aina."""
    pts = _room()
    assert wall_coverage(pts, [], 0.0, 2600.0) == 0.0


def test_coverage_rises_when_a_real_wall_is_added():
    """Mittarin on palkittava seina joka osuu pilven pystypintaan."""
    pts = _room()
    wall = Wall(
        id="w0", confidence=1.0, classification="wall",
        source=ElementSource(method="manual"),
        # Keilain nakee vain SISApinnan (y=0); mallin akseli on seinan keskella
        # eli puoli paksuutta sisapinnasta ulospain.
        axis=[[0.0, -100.0], [6000.0, -100.0]], height=2600.0, thickness=200.0,
        z_min=0.0,
    )
    empty = wall_coverage(pts, [], 0.0, 2600.0)
    with_wall = wall_coverage(pts, [wall], 0.0, 2600.0)
    assert with_wall > empty
    assert with_wall > 0.10


def test_a_wall_in_empty_space_does_not_raise_coverage():
    """Seina jonka alla ei ole pilvea ei saa nostaa lukua — muuten valinta
    palkitsisi keksityista seinista."""
    pts = _room()
    far = Wall(
        id="w1", confidence=1.0, classification="wall",
        source=ElementSource(method="manual"),
        axis=[[0.0, 50_000.0], [6000.0, 50_000.0]], height=2600.0,
        thickness=200.0, z_min=0.0,
    )
    assert wall_coverage(pts, [far], 0.0, 2600.0) == 0.0


def test_single_candidate_skips_measuring():
    """Yhden ehdokkaan tapauksessa ei mitata mitaan — pieni kohde ei saa
    maksaa ylimaaraista ajoa."""
    calls = []
    pipe = Pipeline(PipelineConfig(detector="contour"))
    cloud = _cloud(_room())

    import scan2bim.core.qa.coverage as cov
    real = cov.wall_coverage
    cov.wall_coverage = lambda *a, **k: calls.append(1) or real(*a, **k)
    try:
        model, name = pipe._best_detector(cloud, ["contour"])
    finally:
        cov.wall_coverage = real
    assert name == "contour"
    assert model is not None
    assert calls == []


def test_choice_picks_the_detector_with_more_coverage(monkeypatch):
    """Kahdesta ehdokkaasta valitaan mitattu voittaja, ei listan ensimmainen."""
    from scan2bim.schemas.model import StructuralModel
    import scan2bim.core.segmentation.base as base
    import scan2bim.core.qa.coverage as cov

    scores = {"contour": 0.10, "histogram": 0.80}
    current = {"name": None}

    class _Fake:
        def __init__(self, name):
            self.name = name

        def detect(self, _cloud):
            current["name"] = self.name
            return StructuralModel()

    monkeypatch.setattr(base.DetectorRegistry, "get",
                        staticmethod(lambda n: (lambda: _Fake(n))))
    monkeypatch.setattr(cov, "wall_coverage",
                        lambda *a, **k: scores[current["name"]])

    pipe = Pipeline(PipelineConfig(detector="contour"))
    _model, name = pipe._best_detector(_cloud(_room()), ["contour", "histogram"])
    assert name == "histogram", "valinnan on seurattava mitattua kattavuutta"

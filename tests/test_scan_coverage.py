"""Kattaako malli koko skannatun lattian vai vain osan siita.

Mitattu Rohbau site_07 scene_07000: mallin jalanjaljen sisalla on 17/17
GT-seinaa mutta ulkopuolella 7/32 — malli on TAYDELLINEN sille alueelle jonka
se vaittaa mallintavansa, ja koko vaje on rajauksesta. Kayttajan on nahtava se
tuloksesta, ei vasta vertaamalla pilveen.
"""
import numpy as np
import open3d as o3d

from ordinate.core.qa.deviation import scan_coverage
from ordinate.schemas.model import ElementSource, Slab, StructuralModel, Wall


def _floor_pts(x0, x1, y0, y1, step=200.0, z=0.0, n_per=6):
    x = np.arange(x0, x1, step)
    y = np.arange(y0, y1, step)
    xx, yy = np.meshgrid(x, y)
    pts = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)])
    return np.repeat(pts, n_per, axis=0)


def _cloud(*parts):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pc


def _model(x0, x1, y0, y1):
    ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return StructuralModel(
        walls=[Wall(id="w0", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"),
                    axis=[[x0, y0], [x1, y0]], height=2700.0, thickness=200.0, z_min=0.0)],
        slabs=[Slab(id="s0", confidence=1.0, classification="slab",
                    source=ElementSource(method="manual"), slab_type="floor",
                    boundary=ring, elevation=0.0, thickness=200.0)],
    )


def test_model_covering_the_whole_scan_reports_full_coverage():
    m = _model(0, 10000, 0, 8000)
    cov = scan_coverage(m, _cloud(_floor_pts(200, 9800, 200, 7800)))
    assert cov is not None
    assert cov["covered_frac"] > 0.95, cov
    assert cov["outside_m2"] < 5.0, cov


def test_building_continuing_past_the_model_is_reported():
    """Puolet skannatusta lattiasta mallin ulkopuolella -> osuus ~0.5."""
    m = _model(0, 10000, 0, 8000)
    cloud = _cloud(_floor_pts(200, 9800, 200, 7800),
                   _floor_pts(10400, 20000, 200, 7800))
    cov = scan_coverage(m, cloud)
    assert 0.4 < cov["covered_frac"] < 0.6, cov
    assert cov["outside_m2"] > 50.0, cov
    assert abs(cov["scanned_m2"] - (cov["inside_m2"] + cov["outside_m2"])) < 1.0


def test_areas_are_square_metres():
    """10 x 8 m lattia = 80 m2 — ei mm2 eika solulukuja."""
    m = _model(0, 10000, 0, 8000)
    cov = scan_coverage(m, _cloud(_floor_pts(100, 9900, 100, 7900)))
    assert 70.0 < cov["inside_m2"] < 90.0, cov


def test_too_few_points_returns_none():
    m = _model(0, 10000, 0, 8000)
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.zeros((10, 3)))
    assert scan_coverage(m, pc) is None

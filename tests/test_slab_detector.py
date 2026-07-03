"""Slab-detektion piikinvalinta: katto = vahvin ylapiikki, ei ketjukavelya alaspain."""
import numpy as np
import open3d as o3d
import pytest

from scan2bim.core.segmentation.slab_detector import detect_slabs


_RNG = np.random.RandomState(42)


def _plane(x0, x1, y0, y1, z, step=25.0):
    xs = np.arange(x0, x1, step)
    ys = np.arange(y0, y1, step)
    gx, gy = np.meshgrid(xs, ys)
    zz = z + _RNG.normal(0.0, 4.0, gx.size)
    pts = np.column_stack([gx.ravel(), gy.ravel(), zz])
    return pts


def _cloud(pts):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    return pc


def _wall_pts():
    zs = np.arange(0, 3200, 25.0)
    xs = np.arange(0, 6000, 25.0)
    gx, gz = np.meshgrid(xs, zs)
    return np.column_stack([
        gx.ravel(),
        _RNG.normal(0.0, 4.0, gx.size),
        gz.ravel() + _RNG.normal(0.0, 4.0, gx.size),
    ])


def test_ceiling_peak_at_histogram_top_edge_is_found():
    """Katto on pilven ylin taso → sen piikki osuu histogrammin VIIMEISEEN biniin.
    find_peaks ei tunnista reunabinia piikiksi ilman pehmustusta → katoksi
    valikoituu alempi rakenne (kotelo/kaytavakatto). Oikea vastaus: 3200."""
    ceil = _plane(0, 6000, 0, 6000, 3200.0)
    ceil[:, 2] = 3200.0 - np.abs(ceil[:, 2] - 3200.0)   # kova ylaraja: ei pisteita katon ylapuolella
    parts = [
        _plane(0, 6000, 0, 6000, 0.0),        # lattia (pilven alin taso)
        ceil,                                  # paakatto (pilven ylin taso)
        _plane(0, 3500, 0, 2000, 2700.0),     # kaytavakatto (pienempi, alempana)
    ]
    cloud = _cloud(np.vstack(parts + [_wall_pts()]))

    slabs = detect_slabs(cloud)
    ceiling = next(s for s in slabs if s.slab_type == "ceiling")
    assert abs(ceiling.elevation - 3200.0) < 60.0, (
        f"katto {ceiling.elevation} — reunabinin piikki ohitettiin"
    )
    floor = next(s for s in slabs if s.slab_type == "floor")
    assert abs(floor.elevation - 0.0) < 60.0


def test_ceiling_ignores_weaker_soffit_peak_within_pair_distance():
    """Paakatto 3200 (vahva), kotelo 2800 (heikko, parivalin 450mm sisalla) →
    parikavely EI saa astua heikompaan piikkiin (alakatto-ansa)."""
    parts = [
        _plane(0, 6000, 0, 6000, 0.0),
        _plane(0, 6000, 0, 6000, 3200.0),
        _plane(0, 3500, 0, 2000, 2800.0),     # kotelo 400mm alempana, heikompi
    ]
    cloud = _cloud(np.vstack(parts + [_wall_pts()]))

    slabs = detect_slabs(cloud)
    ceiling = next(s for s in slabs if s.slab_type == "ceiling")
    assert abs(ceiling.elevation - 3200.0) < 60.0, (
        f"katto {ceiling.elevation} — tarttui heikompaan alapiikkiin"
    )


def test_ceiling_steps_down_to_stronger_pair_face():
    """Laattapari: ylapinta 3400 (heikko, esim. ylakerran lattia nakyy aukosta),
    alapinta 3200 (vahva, huoneesta nakyva) → katoksi 3200."""
    parts = [
        _plane(0, 6000, 0, 6000, 0.0),
        _plane(0, 6000, 0, 6000, 3200.0),      # nakyva kattopinta (vahva)
        _plane(0, 2500, 0, 2500, 3400.0),      # laatan ylapinta (heikko)
    ]
    cloud = _cloud(np.vstack(parts + [_wall_pts()]))

    slabs = detect_slabs(cloud)
    ceiling = next(s for s in slabs if s.slab_type == "ceiling")
    assert abs(ceiling.elevation - 3200.0) < 60.0


def test_floor_steps_up_to_stronger_walking_surface():
    """Lattiapari: alapinta -200 (heikko), kavelypinta 0 (vahva) → lattiaksi 0."""
    parts = [
        _plane(0, 2500, 0, 2500, -200.0),      # laatan alapinta (heikko)
        _plane(0, 6000, 0, 6000, 0.0),         # kavelypinta (vahva)
        _plane(0, 6000, 0, 6000, 3200.0),
    ]
    cloud = _cloud(np.vstack(parts + [_wall_pts()]))

    slabs = detect_slabs(cloud)
    floor = next(s for s in slabs if s.slab_type == "floor")
    assert abs(floor.elevation - 0.0) < 60.0

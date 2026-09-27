"""Slab-detektion piikinvalinta: katto = vahvin ylapiikki, ei ketjukavelya alaspain."""
import numpy as np
import open3d as o3d
import pytest

from ordinate.core.segmentation.slab_detector import detect_slabs


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


def test_disjoint_floor_regions_all_returned():
    """Kaksi erillista lattia-aluetta (asunto + viereinen huone paksun seinan
    takana) → molempien kontuurit talteen, ei vain suurinta (perimetri ei
    muuten koskaan sulje pienempaa huonetta)."""
    from ordinate.core.segmentation.slab_detector import detect_floor_contours

    parts = [
        _plane(0, 6000, 0, 6000, 0.0),          # iso lattia
        _plane(6400, 9400, 0, 3000, 0.0),       # pieni huone 400mm seinan takana
    ]
    cloud = _cloud(np.vstack(parts))

    polys = detect_floor_contours(cloud, 0.0)
    assert len(polys) == 2, f"kontuureja {len(polys)}, odotettiin 2"
    areas = sorted(
        abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                for i in range(len(p)))) / 2.0
        for p in polys
    )
    assert areas[0] > 6_000_000, "pienen huoneen kontuuri puuttuu/vajaa"


def test_furniture_shadows_do_not_break_contour():
    """Kalusteiden keilausvarjot syovat lattiaan lahdet ulkoreunaan asti. Ennen
    korjausta ulkokontuuri kiersi joka lahden ja suhteellinen approxPolyDP-epsilon
    romahdutti ne ITSENSA LEIKKAAVAKSI monikulmioksi → signed area (perimetrin
    ULOSPAIN-normaali) meni vaarin ja seinia syntyi fiktiivisille reunoille."""
    from shapely.geometry import Polygon

    from ordinate.core.segmentation.slab_detector import detect_floor_contours

    floor = _plane(0, 8000, 0, 8000, 0.0)   # 8 x 8 m = 64 m²
    # 18 kapeaa lahtea vuorotellen ylä- ja alareunasta, syvyys 3–5 m
    keep = np.ones(len(floor), dtype=bool)
    for k in range(18):
        x0 = 400.0 + k * (7200.0 / 18)
        cut = (floor[:, 0] > x0) & (floor[:, 0] < x0 + 250)
        keep &= ~(cut & ((floor[:, 1] > 3000.0) if k % 2 == 0 else (floor[:, 1] < 5000.0)))
    cloud = _cloud(floor[keep])

    polys = detect_floor_contours(cloud, 0.0)
    assert polys, "kontuuri katosi"
    poly = Polygon(polys[0])
    # vanha koodi: 34 karkea, 24.2 m2, is_valid=False
    assert poly.is_valid, "kontuuri leikkaa itsensa"
    assert poly.area > 55e6, f"huoneala {poly.area / 1e6:.1f} m2, odotettiin ~64 m2"


def test_grid_cell_is_the_default_for_a_dense_scan():
    """25 mm ruutu sailyy aina kun skanni sen kestaa.

    Jokainen skanni jonka nykyinen koodi jo kasittelee kayttaytyy TASMALLEEN
    kuten ennenkin — mitattu: koko Rohbau site_07 -matriisi (5 scenea x 5
    elementtityyppia) on identtinen ennen ja jalkeen.
    """
    from ordinate.core.segmentation.slab_detector import _GRID_MM, _cell_mm
    dense = _plane(0, 6000, 0, 6000, 0.0, step=10.0)[:, :2]
    assert _cell_mm(dense) == _GRID_MM


def test_grid_cell_follows_a_coarse_scan():
    """Karkeammalla skannilla ruutu seuraa pistevalia.

    25 mm ruutu on 70 mm pistevalilla PIENEMPI kuin skannin resoluutio, jolloin
    suurin osa lattian ruuduista on tyhjia eika maski kuvaa lattiaa vaan
    keilaustiheytta.
    """
    from ordinate.core.segmentation.slab_detector import _GRID_MM, _cell_mm
    coarse = _plane(0, 20000, 0, 20000, 0.0, step=70.0)[:, :2]
    cell = _cell_mm(coarse)
    assert cell > _GRID_MM
    assert 55.0 < cell < 90.0, f"ruutu {cell:.0f} mm, pistevali 70 mm"


def test_coarse_floor_still_produces_a_contour():
    """70 mm pistevalilla lattiaa EI loytynyt lainkaan (0 kontuuria).

    Mitattu Rohbau scene_07000 harvennussarjassa: kontuureja 3, 3, 2 ja 0
    pisteväleilla 4, 17, 35 ja 70 mm.
    """
    from ordinate.core.segmentation.slab_detector import detect_floor_contours
    cloud = _cloud(_plane(0, 12000, 0, 9000, 0.0, step=70.0))
    polys = detect_floor_contours(cloud, 0.0)
    assert polys, "karkea lattia ei tuottanut yhtaan kontuuria"
    area = abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                   for p in polys for i in range(len(p)))) / 2.0
    assert area > 80e6, f"kontuurin ala {area / 1e6:.1f} m2, odotettiin ~108"

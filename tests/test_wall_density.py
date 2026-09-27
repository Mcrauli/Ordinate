"""Density-seinädetektio — synteettinen huonepilvi (M4b)."""
import numpy as np
import open3d as o3d

from ordinate.core.segmentation.base import DetectorRegistry
from ordinate.core.segmentation.wall_density import WallDetectorDensity
from ordinate.schemas.model import StructuralModel


def _box_room_cloud(seed: int = 0) -> o3d.geometry.PointCloud:
    rng = np.random.default_rng(seed)
    pts = []
    n = 500
    for _ in range(n):
        pts.append([5000, rng.uniform(0, 4000), rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([0, rng.uniform(0, 4000), rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), 4000, rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), 0, rng.uniform(0, 2800)])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), rng.uniform(0, 4000), 0])
    for _ in range(n):
        pts.append([rng.uniform(0, 5000), rng.uniform(0, 4000), 2800])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(pts, dtype=np.float64))
    return cloud


def test_density_finds_walls():
    cloud = _box_room_cloud()
    model = WallDetectorDensity(grid_size=100.0, min_line_length=1000.0).detect(cloud)
    assert len(model.walls) >= 2


def test_density_returns_structural_model():
    cloud = _box_room_cloud()
    assert isinstance(WallDetectorDensity().detect(cloud), StructuralModel)


def test_density_wall_axis_in_bounds():
    cloud = _box_room_cloud()
    model = WallDetectorDensity(grid_size=100.0, min_line_length=500.0).detect(cloud)
    if not model.walls:
        return
    pts = np.asarray(cloud.points)
    x_lo, x_hi = float(pts[:, 0].min()) - 200, float(pts[:, 0].max()) + 200
    y_lo, y_hi = float(pts[:, 1].min()) - 200, float(pts[:, 1].max()) + 200
    for wall in model.walls:
        for px, py in wall.axis:
            assert x_lo <= px <= x_hi
            assert y_lo <= py <= y_hi


def test_density_wall_schema_valid():
    cloud = _box_room_cloud()
    model = WallDetectorDensity(grid_size=100.0, min_line_length=500.0).detect(cloud)
    for wall in model.walls:
        assert 0.0 <= wall.confidence <= 1.0
        assert wall.height > 0
        assert wall.thickness == 200.0


def test_registry_has_density():
    assert "density" in DetectorRegistry.names()
    assert DetectorRegistry.get("density") is WallDetectorDensity


def test_tall_space_wall_found_beam_rejected():
    """Palkitettu runko: katto 10 m, seina ulottuu vain 3 m. Osuussaanto vaatisi
    0.55 x 10 m = 5.5 m jatkuvuutta → 0 seinaa (mitattu Rohbau3D site_07:lla,
    aidon seinapikselin jatkuvuus mediaani 1.35 m). Korkeassa tilassa riittaa
    absoluuttinen 1500 mm yhtajaksoinen jakso; palkki (1.2 m syva, korkealla) ei
    saa lapaista."""
    import numpy as np
    import open3d as o3d

    from ordinate.core.segmentation.wall_contour import WallDetectorContour

    rng = np.random.RandomState(7)

    def slab(x0, x1, y0, y1, z, n=140000):
        return np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n),
                                z + rng.normal(0, 3.0, n)])

    def wall(x, y0, y1, z0, z1, n=160000):
        return np.column_stack([x + rng.normal(0, 3.0, n), rng.uniform(y0, y1, n),
                                rng.uniform(z0, z1, n)])

    parts = [
        slab(0, 12000, 0, 12000, 0.0),          # lattia
        slab(0, 12000, 0, 12000, 10000.0),      # katto 10 m
        wall(0.0, 0, 12000, 0, 3000),           # seina vain 3 m korkea
        wall(12000.0, 0, 12000, 0, 3000),
        # palkki: korkealla, syvyys 1.2 m, ei ulotu lattiaan
        np.column_stack([rng.uniform(0, 12000, 200000),
                         6000 + rng.normal(0, 3.0, 200000),
                         rng.uniform(8500, 9700, 200000)]),
    ]
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))

    walls = WallDetectorContour().detect(pc).walls
    assert walls, "korkeassa tilassa ei loytynyt yhtaan seinaa"
    # palkki on y=6000 kohdalla ja kulkee x-suunnassa: sielta ei saa tulla seinaa
    beam_like = [w for w in walls
                 if abs((w.axis[0][1] + w.axis[1][1]) / 2 - 6000) < 400
                 and abs(w.axis[1][1] - w.axis[0][1]) < abs(w.axis[1][0] - w.axis[0][0])]
    assert not beam_like, f"palkista tuli seina: {[w.axis for w in beam_like]}"


def test_semantic_labels_relax_vertical_run_in_tall_space():
    """Korkeassa tilassa geometrinen sääntö vaatii 1500 mm yhtajaksoisen
    pystyjakson. Kun PointNetin luokka on tiedossa, palkkien torjunta ei ole
    enaa pelkan jatkuvuuden varassa → riittaa 1000 mm SEINAluokan pisteista.
    Mitattu Rohbau3D-GT:lla: kattavuus 0.260 -> 0.648, tarkkuus 0.962 -> 0.965."""
    import numpy as np
    import open3d as o3d

    from ordinate.core.segmentation.pointnet_filter import S3DIS_WALL, SemanticLabels
    from ordinate.core.segmentation.wall_contour import WallDetectorContour

    rng = np.random.RandomState(11)

    def slab(z, n=140000):
        return np.column_stack([rng.uniform(0, 12000, n), rng.uniform(0, 12000, n),
                                z + rng.normal(0, 3.0, n)])

    def wall(x, z0, z1, n=170000):
        return np.column_stack([x + rng.normal(0, 3.0, n), rng.uniform(0, 12000, n),
                                rng.uniform(z0, z1, n)])

    # kaista alkaa lattia+350 → 1600 mm seinasta jaa kaistaan 1250 mm:
    # alle geometrisen 1500 mm, yli semanttisen 1000 mm
    walls_pts = np.vstack([wall(0.0, 0, 1600), wall(12000.0, 0, 1600)])
    pts = np.vstack([slab(0.0), slab(10000.0), walls_pts])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)

    det = WallDetectorContour()
    assert not det.detect(pc).walls, "geometrinen saanto ei saisi loytaa 1200 mm seinaa"

    pred = np.zeros(len(pts), dtype=np.int64)
    pred[len(pts) - len(walls_pts):] = S3DIS_WALL
    det2 = WallDetectorContour()
    det2.semantic_labels = SemanticLabels.build(pts, pred)
    assert det2.detect(pc).walls, "semanttisilla labeleilla seinan olisi pitanyt loytya"

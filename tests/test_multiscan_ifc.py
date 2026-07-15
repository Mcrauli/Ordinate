"""
Integraatiotesti: generoi 2-kerroksiset raaka-skannaustiedostot (8 skanneria),
ajaa Pipeline.run_floors(), kirjoittaa IFC Solibri-tarkastelua varten.

Kayttö:
    .venv\\Scripts\\python tests\\test_multiscan_ifc.py
    -> data/output/test_multiscan/floor_00/model.ifc   (kerros 1)
    -> data/output/test_multiscan/floor_01/model.ifc   (kerros 2)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

DATA_DIR = ROOT / "data"
RAW_DIR  = DATA_DIR / "raw" / "test_multiscan"
OUT_DIR  = DATA_DIR / "output" / "test_multiscan"

RNG = np.random.default_rng(42)

# --- Rakennusgeometria (mm) --------------------------------------------------
# Pohja: 18 000 x 12 000
# Kerros 1: Z    0 - 3 000  (huonekorkeus 3 000 mm)
# Laatta:   Z 3 000 - 3 300 (300 mm betonilaatta)
# Kerros 2: Z 3 300 - 6 300

_W, _D   = 18_000.0, 12_000.0
_H       = 3_000.0    # kerroksen sisäkorkeus mm
_SLAB    = 300.0      # laattavahvuus mm
_STEP    = 40.0       # pisteiden rasterijako mm
_NOISE   = 6.0        # mm - pistekohina (perus)
_T_OUTER = 300.0      # ulkoseinien paksuus mm
_T_INNER = 150.0      # väliseinien paksuus mm


def _face(x0, y0, x1, y1, z0, z1, cov=0.88, holes=None) -> np.ndarray:
    """Yksi seinäpinta rasteripistein + kohina. holes = lista (a0,a1,h0,h1):
    paikallinen reikä along-etäisyydellä a0..a1 (mm seinän alusta) ja Z-välillä h0..h1."""
    length = np.hypot(x1 - x0, y1 - y0)
    nl = max(int(length / _STEP), 2)
    nz = max(int((z1 - z0) / _STEP), 2)
    t  = np.linspace(0, 1, nl)
    zv = np.linspace(z0, z1, nz)
    tt, zz = np.meshgrid(t, zv)
    xs = x0 + tt * (x1 - x0)
    ys = y0 + tt * (y1 - y0)
    along = tt * length
    keep = np.ones_like(along, dtype=bool)
    if holes:
        for a0, a1, h0, h1 in holes:
            keep &= ~((along >= a0) & (along <= a1) & (zz >= h0) & (zz <= h1))
    pts = np.stack([xs.ravel(), ys.ravel(), zz.ravel()], axis=1)[keep.ravel()]
    pts = pts[RNG.random(len(pts)) < cov]
    pts += RNG.normal(0, _NOISE, pts.shape)
    return pts


def _wall(ax0, ay0, ax1, ay1, z0, z1, thickness=_T_INNER, cov=0.88, holes=None) -> np.ndarray:
    """
    Seinä akselin perusteella: MOLEMMAT pinnat +-thickness/2 sivuilla.
    NormalAssistedDetector tarvitsee molemmat pinnat paritukseen.
    holes karsitaan molemmista pinnoista samasta along/Z-kohdasta.
    """
    dx, dy = ax1 - ax0, ay1 - ay0
    length = np.hypot(dx, dy)
    if length < 1.0:
        return np.zeros((0, 3))
    nx, ny = -dy / length, dx / length   # vasemman puolen normaali
    h = thickness / 2.0

    face1 = _face(ax0 + nx*h, ay0 + ny*h, ax1 + nx*h, ay1 + ny*h, z0, z1, cov, holes)
    face2 = _face(ax0 - nx*h, ay0 - ny*h, ax1 - nx*h, ay1 - ny*h, z0, z1, cov, holes)
    return np.concatenate([face1, face2])


def _column_pts(cx, cy, z0, z1, r=150.0) -> np.ndarray:
    """Pyöreä, vapaasti seisova pilari (kaikki pinnat näkyvät)."""
    nz = max(int((z1 - z0) / _STEP), 2)
    angles = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    zs = np.linspace(z0, z1, nz)
    aa, zz = np.meshgrid(angles, zs)
    xs = cx + r * np.cos(aa)
    ys = cy + r * np.sin(aa)
    pts = np.stack([xs.ravel(), ys.ravel(), zz.ravel()], axis=1)
    pts += RNG.normal(0, _NOISE, pts.shape)
    return pts


def _slab_pts(z) -> np.ndarray:
    xs = np.arange(0, _W, _STEP)
    ys = np.arange(0, _D, _STEP)
    xx, yy = np.meshgrid(xs, ys)
    pts = np.stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)], axis=1)
    pts += RNG.normal(0, _NOISE, pts.shape)
    return pts


def _build_floor(z0: float) -> np.ndarray:
    """Pisteet yhdelle kerrokselle — molemmat seinäpinnat, lattia, katto.
    Aukot: ikkunat ulkoseinissä (sill 900, korkeus 1200), ovet väliseinissä (lattialta 2100)."""
    z1 = z0 + _H
    win = lambda a0, a1: (a0, a1, z0 + 900.0, z0 + 2100.0)   # ikkuna
    door = lambda a0, a1: (a0, a1, z0 - 50.0, z0 + 2100.0)   # ovi (lattialta)
    parts = [
        # Ulkoseinät (paksut, kumpikin pinta) — ikkuna-aukot
        _wall(     0,      0, _W,       0, z0, z1, _T_OUTER,
              holes=[win(2000, 3500), win(7500, 9000), win(13000, 14500)]),   # etela
        _wall(    _W,      0, _W,      _D, z0, z1, _T_OUTER,
              holes=[win(3000, 4500), win(7500, 9000)]),                      # ita
        _wall(    _W,     _D,  0,      _D, z0, z1, _T_OUTER,
              holes=[win(4000, 5500), win(12000, 13500)]),                    # pohjoinen
        _wall(     0,     _D,  0,       0, z0, z1, _T_OUTER,
              holes=[win(4000, 5500)]),                                       # lansi
        # Väliseinät (ohuemmat) — oviaukot
        _wall(  6000,      0,  6000,  8000, z0, z1, _T_INNER, cov=0.85,
              holes=[door(3000, 4000)]),
        _wall( 12000,      0, 12000,  8000, z0, z1, _T_INNER, cov=0.85,
              holes=[door(3000, 4000)]),
        _wall(     0,   8000, _W,     8000, z0, z1, _T_INNER, cov=0.85,
              holes=[door(2500, 3500), door(8500, 9500), door(14500, 15500)]),
        # Vapaasti seisovat pilarit (huoneiden A ja C keskellä)
        _column_pts(4500, 4000, z0, z1),
        _column_pts(13500, 4000, z0, z1),
        # Lattia ja katto
        _slab_pts(z0),
        _slab_pts(z1),
    ]
    return np.concatenate(parts)


def _scanner_noise(pts: np.ndarray, sx, sy, sz) -> np.ndarray:
    """Etäisyyspohjainen skannauskohinamalli: 0.5 mm @ 1 m, 5 mm @ 10 m."""
    d = np.sqrt((pts[:,0]-sx)**2 + (pts[:,1]-sy)**2 + (pts[:,2]-sz)**2)
    sigma = np.clip(d * 0.0005, 0.3, 5.0)
    return pts + RNG.normal(0, sigma[:, None], pts.shape)


def generate_scans() -> list[Path]:
    """Luo 8 PLY-tiedostoa (4 per kerros)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    positions_xy = [
        (3_000.0,  4_000.0),    # Huone A
        (9_000.0,  4_000.0),    # Huone B
        (15_000.0, 4_000.0),    # Huone C
        (9_000.0, 10_000.0),    # Kaytava
    ]

    floor1_pts = _build_floor(0.0)
    floor2_pts = _build_floor(_H + _SLAB)

    paths: list[Path] = []
    idx = 0
    for (all_pts, z_mid) in [
        (floor1_pts, _H / 2),
        (floor2_pts, _H + _SLAB + _H / 2),
    ]:
        for sx, sy in positions_xy:
            sz = z_mid
            dist = np.sqrt((all_pts[:,0]-sx)**2 + (all_pts[:,1]-sy)**2 + (all_pts[:,2]-sz)**2)
            visible = all_pts[dist < 15_000.0]
            noisy   = _scanner_noise(visible, sx, sy, sz)

            cloud = o3d.geometry.PointCloud()
            cloud.points = o3d.utility.Vector3dVector(noisy)

            p = RAW_DIR / f"scan_{idx:02d}.ply"
            o3d.io.write_point_cloud(str(p), cloud)
            print(f"  {p.name}: {len(noisy):,} pistetta")
            paths.append(p)
            idx += 1

    return paths


def test_multiscan_pipeline_produces_ifc():
    """Ajaa koko putken ja kirjoittaa IFC — tarkasta Solibrissa."""
    from scan2bim.core.pipeline import Pipeline, PipelineConfig

    print(f"\nGeneroidaan skannaustiedostot -> {RAW_DIR}")
    paths = generate_scans()
    print(f"Generoitu {len(paths)} tiedostoa.")

    config = PipelineConfig(
        voxel_size=3.0,     # 3 mm — nopea testi, riittaa visuaaliseen tarkistukseen
        detector="normals",
        export_ifc=True,
        export_dxf=True,
    )

    pipeline = Pipeline(config, progress=lambda m: print(f"  {m}"))
    models = pipeline.run_floors(paths, OUT_DIR)

    assert len(models) >= 1, "Ei löydetty yhtään kerrosta"

    for i, m in enumerate(models):
        ifc = OUT_DIR / f"floor_{i:02d}" / "model.ifc"
        assert ifc.exists(), f"IFC puuttuu: {ifc}"
        assert len(m.walls) >= 3, f"Kerros {i}: liian vähän seiniä ({len(m.walls)})"
        assert len(m.columns) == 2, f"Kerros {i}: pilareita {len(m.columns)}, odotettiin 2"
        print(f"\nKerros {i}: {m.summary()}")
        print(f"IFC: {ifc}")

    # Georef-leima: oletus EPSG:3067, MapConversion mm->m, geometria koskematta
    import ifcopenshell
    f = ifcopenshell.open(str(OUT_DIR / "building.ifc"))
    crs = f.by_type("IfcProjectedCRS")
    mc = f.by_type("IfcMapConversion")
    assert crs and crs[0].Name == "EPSG:3067", "georef-leima (EPSG:3067) puuttuu"
    assert mc and abs(mc[0].Scale - 0.001) < 1e-9, "MapConversion mm->m skaala vaarin"
    assert mc[0].Eastings == 0.0 and mc[0].Northings == 0.0, "offset ei 0 (geometria siirtyi)"

    print(f"\nAvaa Solibrissa:")
    for i in range(len(models)):
        print(f"  {OUT_DIR / f'floor_{i:02d}' / 'model.ifc'}")


if __name__ == "__main__":
    test_multiscan_pipeline_produces_ifc()


def test_diagnostics_report_written(tmp_path):
    """Jaettava diagnostiikkaraportti syntyy joka ajosta eika sisalla
    koordinaatteja (pilotti ei voi jakaa skanneja — taman voi)."""
    import numpy as np
    import open3d as o3d
    from scan2bim.core.pipeline import Pipeline, PipelineConfig

    rng = np.random.RandomState(4)
    parts = []
    for axis, fixed, lo, hi in [(0, 0, 0, 4000), (0, 5000, 0, 4000),
                                (1, 0, 0, 5000), (1, 4000, 0, 5000)]:
        n = 20000
        u = rng.uniform(lo, hi, n); v = rng.uniform(0, 2700, n)
        w = (np.column_stack([np.full(n, fixed) + rng.normal(0, 3, n), u, v]) if axis == 0
             else np.column_stack([u, np.full(n, fixed) + rng.normal(0, 3, n), v]))
        parts.append(w)
    xy = rng.uniform([0, 0], [5000, 4000], (30000, 2))
    parts.append(np.column_stack([xy, rng.normal(0, 3, 30000)]))
    parts.append(np.column_stack([xy, 2700 + rng.normal(0, 3, 30000)]))
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))
    ply = tmp_path / "huone.ply"
    o3d.io.write_point_cloud(str(ply), pc)

    cfg = PipelineConfig(auto_voxel=True, detector="contour", export_ifc=False,
                         export_dxf=False, export_qa=False, semantic_filter_mode="off")
    Pipeline(cfg).run_floors([ply], tmp_path / "out")

    rep = tmp_path / "out" / "diagnostics.txt"
    assert rep.exists(), "diagnostics.txt puuttuu"
    txt = rep.read_text(encoding="utf-8")
    assert "versio:" in txt and "syötteet:" in txt
    assert "Seinädetektio" in txt or "kerros" in txt.lower()


def test_retail_filter_variant_loads():
    """pointnet-retail-variantti lataa oman mallinsa ja poistaa hyllyt;
    puuttuessa fallback oletusmalliin."""
    from scan2bim.core.segmentation.pointnet_filter import PointNetFilter, _find_model_path
    assert _find_model_path("retail") is not None, "retail-mallia ei loydy"
    f = PointNetFilter(variant="retail")
    assert f.is_available()


def test_corner_extensions_butt_joints():
    from scan2bim.core.ifc.writer import _corner_extensions
    from scan2bim.schemas.model import ElementSource, Wall

    def w(wid, x0, y0, x1, y1, t):
        return Wall(id=wid, confidence=0.9, classification="wall",
                    source=ElementSource(method="contour"),
                    axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=t, z_min=0.0)

    # L-nurkka (0,0): paksumpi a jatkuu labi (+t_b/2), b katkaistaan (-t_a/2)
    a = w("a", -3000, 0, 0, 0, 200.0)
    b = w("b", 0, 0, 0, 2500, 100.0)
    ext = _corner_extensions([a, b])
    assert abs(ext["a"][1] - 50.0) < 1.0, f"labimeneva ei jatku: {ext}"
    assert abs(ext["b"][0] + 100.0) < 1.0, f"katkaisu vaarin: {ext}"

    # T-liitos: c:n paa osuu a:n keskelle -> katkaistaan a:n pintaan
    c = w("c", -1500, 0, -1500, 1800, 100.0)
    ext = _corner_extensions([a, c])
    assert abs(ext["c"][0] + 100.0) < 1.0, f"T-katkaisu vaarin: {ext}"
    assert ext["a"] == (0.0, 0.0) or abs(ext["a"][0]) < 1.0, f"labimeneva muuttui: {ext}"

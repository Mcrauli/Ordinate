"""_trim_endpoints: trimming is evidence-based but must never collapse a wall.

Regression: a perimeter wall with no scan data on its own faces picked up the
points of a CROSSING perpendicular wall (within the +-30mm face band at the
intersection) -> 2%/98% percentiles collapsed a 4m wall to 79mm."""
import numpy as np

from scan2bim.core.pipeline import _trim_endpoints
from scan2bim.schemas.model import ElementSource, Wall


def _wall(x0, y0, x1, y1, method="floorplan"):
    return Wall(
        id="w", confidence=1.0, classification="wall",
        source=ElementSource(method=method),
        axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=200.0, z_min=0.0,
    )


def _crossing_cluster(x=1500.0):
    rng = np.random.RandomState(0)
    n = 200
    return np.column_stack([
        rng.uniform(x - 60, x + 60, n),
        rng.uniform(-110, 110, n),
        rng.uniform(0, 2700, n),
    ])


def test_trim_does_not_collapse_wall_to_crossing():
    wall = _wall(0, 0, 3000, 0)
    out = _trim_endpoints(wall, _crossing_cluster())
    p0, p1 = np.array(out.axis[0]), np.array(out.axis[1])
    length = float(np.linalg.norm(p1 - p0))
    assert length >= 2400.0, f"seina romahti {length:.0f}mm:iin risteyspisteista"


def test_trim_still_trims_real_overshoot():
    rng = np.random.RandomState(1)
    n = 4000
    pts = np.column_stack([
        rng.uniform(0, 2800, n),
        np.where(rng.rand(n) < 0.5, -100.0, 100.0) + rng.normal(0, 3, n),
        rng.uniform(0, 2700, n),
    ])
    wall = _wall(0, 0, 3000, 0, method="contour")
    out = _trim_endpoints(wall, pts)
    p1 = np.array(out.axis[1])
    assert p1[0] < 2900.0, "aito ylitys jai trimmaamatta"


def test_trim_ignores_floor_slab_strip():
    """Seinän x-kaistalla kulkee lattia/kattolaatta (pisteitä joka y:llä
    lattia- ja kattotasossa). Trimmin pitää mitata seinän pää KESKIKORKEUDELTA
    (vain seinäpinta), ei antaa laatan venyttää seinää tilan syvyyden yli."""
    rng = np.random.RandomState(3)
    n_wall = 8000
    # aito seinä y in [0, 3000], KOKO korkeus 0..2700
    wall_pts = np.column_stack([
        rng.uniform(0, 3000, n_wall),
        np.where(rng.rand(n_wall) < 0.5, -100.0, 100.0) + rng.normal(0, 3, n_wall),
        rng.uniform(0, 2700, n_wall),
    ])
    # lattialaatta seinän jatkeena y in [3000, 9000], VAIN lattiataso (z≈0)
    n_slab = 8000
    slab_pts = np.column_stack([
        rng.uniform(3000, 9000, n_slab),
        rng.uniform(-100, 100, n_slab),
        rng.uniform(0, 60, n_slab),
    ])
    pts = np.vstack([wall_pts, slab_pts])
    wall = _wall(0, 0, 9000, 0, method="contour")   # akseli venytetty laatan yli
    out = _trim_endpoints(wall, pts)
    p1 = np.array(out.axis[1])
    assert p1[0] < 3600.0, f"lattialaatta venytti seinän {p1[0]:.0f}mm:iin (odotus ~3000)"


def test_trim_cuts_large_phantom_overshoot():
    """Iso myymälä: seinän akseli venyi metrejä yli datan tyhjän lattian yli.
    Kun kaista on kiistatta aito (pitkä + tiheä), leikkaus saa ylittää 300 mm."""
    rng = np.random.RandomState(2)
    n = 20000
    # Aito seinä x in [40000, 72000] (32 m), akseli venyy 0 -> 120000 (48 m yli)
    pts = np.column_stack([
        rng.uniform(40000, 72000, n),
        np.where(rng.rand(n) < 0.5, -100.0, 100.0) + rng.normal(0, 3, n),
        rng.uniform(0, 2700, n),
    ])
    wall = _wall(0, 0, 120000, 0, method="contour")
    out = _trim_endpoints(wall, pts)
    p0, p1 = np.array(out.axis[0]), np.array(out.axis[1])
    assert p0[0] > 39000.0 and p0[0] < 41000.0, f"p0 ei leikkautunut datan alkuun: {p0[0]:.0f}"
    assert p1[0] > 71000.0 and p1[0] < 73000.0, f"p1 ei leikkautunut datan loppuun: {p1[0]:.0f}"

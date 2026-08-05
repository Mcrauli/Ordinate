"""Histogrammi-detektori: deterministinen, akselinmukaiset seinät tiheyspiikeistä.
Korvaa RANSACin liiketilassa (deterministinen + nopea + pilarivapaa)."""
import numpy as np
import open3d as o3d

from scan2bim.core.segmentation.wall_histogram import WallDetectorHistogram


def _room_cloud(theta=0.0, seed=0):
    """Suorakulmainen huone (8×5 m, 2.7 m korkea) neljällä seinällä, valinnainen kierto."""
    rng = np.random.RandomState(seed)
    walls = []
    for p0, p1 in (((0, 0), (8000, 0)), ((8000, 0), (8000, 5000)),
                   ((8000, 5000), (0, 5000)), ((0, 5000), (0, 0))):
        p0 = np.array(p0, float); p1 = np.array(p1, float)
        n = 6000
        t = rng.uniform(0, 1, n)[:, None]
        line = p0 + t * (p1 - p0)
        d = p1 - p0; nrm = np.array([-d[1], d[0]]); nrm /= np.linalg.norm(nrm)
        line = line + nrm * rng.normal(0, 2, n)[:, None]
        z = rng.uniform(0, 2700, n)[:, None]
        walls.append(np.hstack([line, z]))
    xyz = np.vstack(walls)
    if theta:
        R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        xyz = xyz.copy(); xyz[:, :2] = xyz[:, :2] @ R.T
    c = o3d.geometry.PointCloud()
    c.points = o3d.utility.Vector3dVector(xyz)
    return c


def _sig(model):
    return [(round(w.axis[0][0], 1), round(w.axis[0][1], 1),
             round(w.axis[1][0], 1), round(w.axis[1][1], 1), round(w.thickness, 1))
            for w in model.walls]


def test_histogram_is_deterministic():
    cloud = _room_cloud()
    sigs = [_sig(WallDetectorHistogram().detect(cloud)) for _ in range(4)]
    assert all(s == sigs[0] for s in sigs), "histogrammi-detektori ei ollut deterministinen"


def test_histogram_finds_four_walls():
    model = WallDetectorHistogram().detect(_room_cloud())
    assert len(model.walls) == 4, f"neljän seinän huoneesta löytyi {len(model.walls)}"


def test_histogram_handles_rotation():
    # 20° kierretty huone → rotaationhaku kohdistaa → silti 4 seinää
    model = WallDetectorHistogram().detect(_room_cloud(theta=np.radians(20)))
    assert len(model.walls) >= 4, f"kierretystä huoneesta löytyi vain {len(model.walls)}"


def test_histogram_no_walls_from_flat_slab():
    # pelkkä lattia (matala) → ei seiniä
    rng = np.random.RandomState(0)
    flat = np.column_stack([rng.uniform(0, 8000, 20000), rng.uniform(0, 5000, 20000),
                            rng.uniform(0, 50, 20000)])
    c = o3d.geometry.PointCloud(); c.points = o3d.utility.Vector3dVector(flat)
    assert len(WallDetectorHistogram().detect(c).walls) == 0

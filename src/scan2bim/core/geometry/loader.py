"""Pistepilvi-loaderi: E57 / LAS/LAZ / PTS / PLY → open3d.PointCloud (mm).

Automaattinen yksikkömuunnos: jos pistedata vaikuttaa olevan metreissä
(bounding box max < 500), skaalataan × 1000 → millimetreiksi.
Kynnys 500 m = realistinen yläraja rakennukselle metreissä.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d

log = logging.getLogger(__name__)

# Alle tämän max-dimension → todennäköisesti metrissä → skaala × 1000
_METER_SCALE_THRESHOLD = 500.0


def load_point_cloud(path: Path) -> o3d.geometry.PointCloud:
    """Lataa pistepilvi tiedostosta formaatista riippumatta. Palauttaa mm-koordinaatit."""
    suffix = path.suffix.lower()

    if suffix == ".e57":
        cloud = _load_e57(path)
    elif suffix in {".las", ".laz"}:
        cloud = _load_las(path)
    elif suffix in {".pts", ".xyz"}:
        cloud = _load_pts_xyz(path)
    elif suffix in {".ply", ".pcd"}:
        cloud = o3d.io.read_point_cloud(str(path))
    else:
        raise ValueError(f"Tuntematon formaatti: {suffix}")

    return _ensure_mm(cloud)


def _ensure_mm(cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """Skaalaa metrinen pistepilvi millimetreiksi heuristiikalla."""
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return cloud
    max_dim = float(np.ptp(pts, axis=0).max())   # suurin vaihteluväli
    if max_dim < _METER_SCALE_THRESHOLD:
        log.info(
            "Yksikkömuunnos: max dimension %.2f → näyttää metriltä, skaala × 1000", max_dim
        )
        cloud.points = o3d.utility.Vector3dVector(pts * 1000.0)
    return cloud


def _load_e57(path: Path) -> o3d.geometry.PointCloud:
    import pye57
    e57 = pye57.E57(str(path))
    data = e57.read_scan(0, ignore_missing_fields=True)
    xyz = np.column_stack([data["cartesianX"], data["cartesianY"], data["cartesianZ"]])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return cloud


def _load_pts_xyz(path: Path) -> o3d.geometry.PointCloud:
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            try:
                rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                continue
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(rows, dtype=np.float64))
    return cloud


def _load_las(path: Path) -> o3d.geometry.PointCloud:
    import laspy
    las = laspy.read(str(path))
    xyz = np.column_stack([las.x, las.y, las.z])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return cloud

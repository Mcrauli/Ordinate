"""Pistepilvi-loaderi: E57 / LAS/LAZ / PTS / PLY → open3d.PointCloud."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import open3d as o3d


def load_point_cloud(path: Path) -> o3d.geometry.PointCloud:
    """Lataa pistepilvi tiedostosta formaatista riippumatta."""
    suffix = path.suffix.lower()

    if suffix == ".e57":
        return _load_e57(path)
    if suffix in {".las", ".laz"}:
        return _load_las(path)
    if suffix in {".pts", ".ply", ".pcd", ".xyz"}:
        return o3d.io.read_point_cloud(str(path))

    raise ValueError(f"Tuntematon formaatti: {suffix}")


def _load_e57(path: Path) -> o3d.geometry.PointCloud:
    import pye57
    e57 = pye57.E57(str(path))
    data = e57.read_scan(0, ignore_missing_fields=True)
    xyz = np.column_stack([data["cartesianX"], data["cartesianY"], data["cartesianZ"]])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return cloud


def _load_las(path: Path) -> o3d.geometry.PointCloud:
    import laspy
    las = laspy.read(str(path))
    xyz = np.column_stack([las.x, las.y, las.z])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return cloud

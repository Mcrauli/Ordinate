"""Pistepilvi-loaderi: E57 / LAS/LAZ / PTS / PLY → open3d.PointCloud."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import open3d as o3d


def _autoscale(cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """Jos pilvi on metreissä (max laajuus < 200), skaalaa → mm."""
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return cloud
    span = pts.max(axis=0) - pts.min(axis=0)
    if span.max() < 200.0:
        cloud.points = o3d.utility.Vector3dVector(pts * 1000.0)
    return cloud


def load_and_merge(paths: list[Path]) -> o3d.geometry.PointCloud:
    """Lataa useita pistepilviä ja yhdistää ne yhdeksi."""
    merged = o3d.geometry.PointCloud()
    for p in paths:
        merged += load_point_cloud(p)
    return merged


def load_point_cloud(path: Path) -> o3d.geometry.PointCloud:
    """Lataa pistepilvi tiedostosta formaatista riippumatta."""
    suffix = path.suffix.lower()

    if suffix == ".e57":
        return _autoscale(_load_e57(path))
    if suffix in {".las", ".laz"}:
        return _autoscale(_load_las(path))
    if suffix in {".pts", ".xyz"}:
        return _autoscale(_load_pts_xyz(path))
    if suffix in {".ply", ".pcd"}:
        return _autoscale(o3d.io.read_point_cloud(str(path)))

    raise ValueError(f"Tuntematon formaatti: {suffix}")


def _load_e57(path: Path) -> o3d.geometry.PointCloud:
    import pye57
    e57 = pye57.E57(str(path))
    merged = o3d.geometry.PointCloud()
    for i in range(e57.scan_count):
        try:
            data = e57.read_scan(i, transform=True, ignore_missing_fields=True)
        except Exception:
            data = e57.read_scan(i, ignore_missing_fields=True)
        xyz = np.column_stack([data["cartesianX"], data["cartesianY"], data["cartesianZ"]])
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
        merged += cloud
    return merged


def scanner_origins(path: Path) -> list[np.ndarray]:
    """E57:n skannerien origot (mm). Muut formaatit → tyhjä (ei pose-tietoa)."""
    if path.suffix.lower() != ".e57":
        return []
    try:
        import pye57
        e57 = pye57.E57(str(path))
    except Exception:
        return []
    origins: list[np.ndarray] = []
    for i in range(e57.scan_count):
        try:
            header = e57.get_header(i)
            t = np.asarray(header.translation, dtype=float)
            if np.linalg.norm(t) < 200.0:   # metreissä → mm
                t = t * 1000.0
            origins.append(t)
        except Exception:
            continue
    return origins


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

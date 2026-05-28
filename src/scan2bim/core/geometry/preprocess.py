"""Normalisointi, voxel-downsample ja kohinasuodatus."""
from __future__ import annotations

import numpy as np
import open3d as o3d


def preprocess(
    cloud: o3d.geometry.PointCloud,
    voxel_size: float = 20.0,      # mm
    nb_neighbors: int = 20,
    std_ratio: float = 2.0,
) -> o3d.geometry.PointCloud:
    """Normalisoi → downsample → poista kohina."""
    cloud = _normalize(cloud)
    cloud = cloud.voxel_down_sample(voxel_size=voxel_size)
    cloud, _ = cloud.remove_statistical_outlier(
        nb_neighbors=nb_neighbors, std_ratio=std_ratio
    )
    return cloud


def _normalize(cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """Siirtää pilven origoon (min xyz = 0)."""
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return cloud
    pts -= pts.min(axis=0)
    cloud.points = o3d.utility.Vector3dVector(pts)
    return cloud

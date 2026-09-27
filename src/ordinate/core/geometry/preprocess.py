"""Normalisointi, voxel-downsample ja kohinasuodatus."""
from __future__ import annotations

import numpy as np
import open3d as o3d


def preprocess(
    cloud: o3d.geometry.PointCloud,
    voxel_size: float = 1.0,       # mm
) -> o3d.geometry.PointCloud:
    """Downsample + statistical outlier removal."""
    cloud = cloud.voxel_down_sample(voxel_size=voxel_size)
    cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    return cloud

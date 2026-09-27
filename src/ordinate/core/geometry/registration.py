"""ICP-hienorekisteröinti: tarkentaa skannauksen karkeasta E57-posesta.

Sekvenssirekisteröinti: kukin uusi skannaus kohdistetaan kasvavaan referenssiin
coarse→fine point-to-plane ICP:llä. Poistaa kahdentumat jotka syntyvät kun
skannerin pose heittää muutaman mm/asteen.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

# (max_correspondence_dist mm, downsample voxel mm) karkeasta tarkkaan
_SCHEDULE = ((300.0, 60.0), (120.0, 25.0), (40.0, 8.0))
_MIN_FITNESS = 0.30   # alle tämän: ICP epäonnistui → pidä alkuperäinen pose


def _prep(cloud: o3d.geometry.PointCloud, voxel: float) -> o3d.geometry.PointCloud:
    c = cloud.voxel_down_sample(voxel)
    c.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 3.0, max_nn=30)
    )
    return c


def refine_transform(
    source: o3d.geometry.PointCloud,
    target: o3d.geometry.PointCloud,
    init: np.ndarray | None = None,
) -> tuple[np.ndarray, float, float]:
    """Point-to-plane ICP coarse→fine. Palauttaa (4x4 muunnos, fitness, inlier_rmse)."""
    T = np.eye(4) if init is None else np.asarray(init, dtype=np.float64)
    fitness, rmse = 0.0, 0.0
    for max_corr, voxel in _SCHEDULE:
        s = _prep(source, voxel)
        t = _prep(target, voxel)
        reg = o3d.pipelines.registration.registration_icp(
            s, t, max_corr, T,
            o3d.pipelines.registration.TransformationEstimationPointToPlane(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=40),
        )
        T, fitness, rmse = reg.transformation, reg.fitness, reg.inlier_rmse
    return T, float(fitness), float(rmse)


def align_to_reference(
    slice_cloud: o3d.geometry.PointCloud,
    reference: o3d.geometry.PointCloud,
) -> o3d.geometry.PointCloud:
    """Kohdistaa siivun referenssiin ICP:llä; epäonnistuessa palauttaa ennallaan."""
    if len(reference.points) < 500 or len(slice_cloud.points) < 500:
        return slice_cloud
    T, fitness, _ = refine_transform(slice_cloud, reference)
    if fitness < _MIN_FITNESS:
        return slice_cloud
    return slice_cloud.transform(T)

"""Kirjoittaa detektoidut rakenteet debug-pistepilvenä PLY-muodossa CloudCompareen."""
from __future__ import annotations

import numpy as np
import open3d as o3d
from pathlib import Path

from ordinate.schemas.model import StructuralModel


def write_debug_cloud(model: StructuralModel, path: Path, floor_z: float = 0.0, z_offset: float = 0.0) -> None:
    pts: list[np.ndarray] = []
    colors: list[np.ndarray] = []

    green = np.array([0.0, 1.0, 0.0])
    blue  = np.array([0.0, 0.4, 1.0])

    for wall in model.walls:
        if len(wall.axis) < 2:
            continue
        local_z = floor_z + z_offset
        p0 = np.array([wall.axis[0][0], wall.axis[0][1], local_z])
        p1 = np.array([wall.axis[1][0], wall.axis[1][1], local_z])
        n = max(int(np.linalg.norm(p1 - p0) / 50), 2)
        for i in range(n + 1):
            t = i / n
            pt = p0 + t * (p1 - p0)
            # pilari koko seinän korkeudelle 100mm välein
            h_steps = max(int(wall.height / 100), 2)
            for j in range(h_steps + 1):
                pts.append(pt + np.array([0, 0, j * wall.height / h_steps]))
                colors.append(green)

    for slab in model.slabs:
        if len(slab.boundary) < 3:
            continue
        bnd = np.array(slab.boundary)
        for i in range(len(bnd)):
            p0 = np.append(bnd[i], slab.elevation + z_offset)
            p1 = np.append(bnd[(i + 1) % len(bnd)], slab.elevation + z_offset)
            n = max(int(np.linalg.norm(p1[:2] - p0[:2]) / 100), 2)
            for k in range(n + 1):
                pts.append(p0 + k / n * (p1 - p0))
                colors.append(blue)

    if not pts:
        return

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(pts))
    cloud.colors = o3d.utility.Vector3dVector(np.array(colors))
    o3d.io.write_point_cloud(str(path), cloud)

"""Seinädetektio 2D-tiheysanalyysi + morfologia + HoughLinesP. Sisään: o3d.PointCloud → ulos: StructuralModel."""
from __future__ import annotations

import cv2
import numpy as np
import open3d as o3d

from ordinate.schemas.model import ElementSource, Metadata, StructuralModel, Wall

from .base import DetectorRegistry, ElementDetector

_GRID_SIZE = 30.0           # mm/pikseli
_DENSITY_THRESHOLD = 3      # min pistettä per pikseli
_MORPH_KERNEL = 5           # morfologinen ydin (pikseleinä)
_MIN_LINE_MM = 1500.0       # mm — lyhyemmät hylätään
_MIN_WALL_HEIGHT = 1500.0   # mm


@DetectorRegistry.register("density")
class WallDetectorDensity(ElementDetector):
    def __init__(
        self,
        grid_size: float = _GRID_SIZE,
        density_threshold: int = _DENSITY_THRESHOLD,
        min_line_length: float = _MIN_LINE_MM,
        min_wall_height: float = _MIN_WALL_HEIGHT,
    ) -> None:
        self.grid_size = grid_size
        self.density_threshold = density_threshold
        self.min_line_length = min_line_length
        self.min_wall_height = min_wall_height

    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        pts = np.asarray(cloud.points)
        if len(pts) == 0:
            return StructuralModel()

        wall_pts = self._filter_wall_heights(pts)
        binary, x_min, y_min = self._to_binary(wall_pts)
        lines_px = self._hough(binary)
        walls = self._to_walls(lines_px, x_min, y_min, pts)
        model = StructuralModel(walls=walls)
        model.metadata = Metadata(detector_method="density")
        return model

    def _filter_wall_heights(self, pts: np.ndarray) -> np.ndarray:
        z_min, z_max = pts[:, 2].min(), pts[:, 2].max()
        if z_max - z_min < self.min_wall_height:
            return pts
        lo = z_min + (z_max - z_min) * 0.1
        hi = z_max - (z_max - z_min) * 0.1
        mask = (pts[:, 2] > lo) & (pts[:, 2] < hi)
        return pts[mask] if mask.sum() > 10 else pts

    def _to_binary(self, pts: np.ndarray) -> tuple[np.ndarray, float, float]:
        x, y = pts[:, 0], pts[:, 1]
        x_min, y_min = float(x.min()), float(y.min())
        cols = max(int((x.max() - x_min) / self.grid_size) + 1, 1)
        rows = max(int((y.max() - y_min) / self.grid_size) + 1, 1)
        grid, _, _ = np.histogram2d(
            x, y, bins=[cols, rows],
            range=[[x_min, x_min + cols * self.grid_size],
                   [y_min, y_min + rows * self.grid_size]],
        )
        binary = (grid.T >= self.density_threshold).astype(np.uint8) * 255
        kernel = np.ones((_MORPH_KERNEL, _MORPH_KERNEL), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return binary, x_min, y_min

    def _hough(self, binary: np.ndarray):
        min_px = max(int(self.min_line_length / self.grid_size), 1)
        return cv2.HoughLinesP(
            binary, rho=1, theta=np.pi / 180, threshold=min_px,
            minLineLength=min_px, maxLineGap=max(int(min_px * 0.5), 1),
        )

    def _to_walls(self, lines_px, x_min: float, y_min: float, all_pts: np.ndarray) -> list[Wall]:
        if lines_px is None:
            return []
        z_min = float(all_pts[:, 2].min())
        z_max = float(all_pts[:, 2].max())
        height = z_max - z_min
        walls: list[Wall] = []
        for idx, line in enumerate(lines_px):
            x0_px, y0_px, x1_px, y1_px = line[0]
            x0 = x_min + x0_px * self.grid_size
            y0 = y_min + y0_px * self.grid_size
            x1 = x_min + x1_px * self.grid_size
            y1 = y_min + y1_px * self.grid_size
            length = float(np.hypot(x1 - x0, y1 - y0))
            if length < self.min_line_length:
                continue
            walls.append(Wall(
                id=f"wall_{idx:03d}",
                confidence=round(min(1.0, length / 5000.0), 3),
                classification="wall",
                source=ElementSource(method="density"),
                axis=[[round(x0, 1), round(y0, 1)], [round(x1, 1), round(y1, 1)]],
                height=round(height, 1),
                thickness=200.0,
                z_min=round(z_min, 1),
            ))
        return walls

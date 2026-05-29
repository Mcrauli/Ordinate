"""DBSCAN-pohjainen pilaridetektori.

Algoritmi:
  1. DBSCAN koko pistepilvestä XY-tasossa.
  2. Pienet kompaktit klusterit → pilari-ehdokkaat.
  3. Suodatusehto: footprint ≤ max_footprint_mm molemmissa suunnissa
     JA aspektisuhde ≤ max_aspect_ratio JA z-ulottuvuus ≥ min_height.
  4. Profiili: ympyrä (jos footprint lähellä neliötä) tai suorakaide.
"""
from __future__ import annotations

import uuid
import logging

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import Column, ColumnProfile, ElementSource
from .base import ElementDetector

log = logging.getLogger(__name__)

_MAX_FOOTPRINT_MM = 700.0    # max pilarin leveys/syvyys
_MAX_ASPECT_RATIO = 2.5      # max leveys/syvyys — yli tämän = seinäfragmentti
_MIN_HEIGHT_MM = 600.0       # min pilarin korkeus
_CIRCLE_RATIO = 1.3          # width/depth < tämä → pyöreä profiili
_MIN_INLIERS = 50            # klusterin minimimäärä pisteitä


class ColumnDetector(ElementDetector):
    """Löytää pilarit DBSCAN-klusteroinnilla."""

    def __init__(
        self,
        eps_mm: float = 80.0,       # DBSCAN-ympäristösäde
        min_points: int = 30,       # DBSCAN-minimipisteet
    ) -> None:
        self.eps_mm = eps_mm
        self.min_points = min_points

    def detect(self, cloud: o3d.geometry.PointCloud) -> list[Column]:
        pts = np.asarray(cloud.points)
        if len(pts) < self.min_points:
            return []

        # DBSCAN XY-tasoon projisoituna: pisteet eri korkeuksilla samassa pilarissa
        pts_xy = pts.copy()
        pts_xy[:, 2] = 0.0
        cloud_2d = o3d.geometry.PointCloud()
        cloud_2d.points = o3d.utility.Vector3dVector(pts_xy)
        labels = np.asarray(cloud_2d.cluster_dbscan(
            eps=self.eps_mm,
            min_points=self.min_points,
            print_progress=False,
        ))

        columns: list[Column] = []
        unique = set(labels.tolist())
        unique.discard(-1)

        for label in unique:
            mask = labels == label
            cluster = pts[mask]
            col = self._cluster_to_column(cluster, label)
            if col is not None:
                columns.append(col)

        log.info("ColumnDetector: %d pilaria löytyi (%d klusterista)", len(columns), len(unique))
        return columns

    # ------------------------------------------------------------------ #

    def _cluster_to_column(self, pts: np.ndarray, label: int) -> Column | None:
        if len(pts) < _MIN_INLIERS:
            return None

        xy = pts[:, :2]
        mn = xy.min(axis=0)
        mx = xy.max(axis=0)
        w, d = float(mx[0] - mn[0]), float(mx[1] - mn[1])

        if w > _MAX_FOOTPRINT_MM or d > _MAX_FOOTPRINT_MM:
            return None
        if w < 50 or d < 50:
            return None

        ratio = max(w, d) / (min(w, d) + 1e-6)
        if ratio > _MAX_ASPECT_RATIO:
            return None

        z_min = float(pts[:, 2].min())
        z_max = float(pts[:, 2].max())
        height = z_max - z_min
        if height < _MIN_HEIGHT_MM:
            return None

        center_xy = ((mn + mx) / 2).tolist()
        shape: str = "circle" if ratio < _CIRCLE_RATIO else "rect"
        dim = round(max(w, d), 1)
        profile = ColumnProfile(
            shape=shape,
            width=round(w, 1),
            depth=round(d, 1) if shape == "rect" else round(dim, 1),
        )

        confidence = round(min(1.0, len(pts) / 2000.0), 3)
        return Column(
            id=str(uuid.uuid4()),
            confidence=confidence,
            source=ElementSource(method="cluster", plane_ids=[label]),
            location=[round(center_xy[0], 1), round(center_xy[1], 1)],
            base_z=round(z_min, 1),
            height=round(height, 1),
            profile=profile,
        )

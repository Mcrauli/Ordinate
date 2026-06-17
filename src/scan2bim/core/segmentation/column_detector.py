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
_CIRCLE_RATIO = 1.3          # width/depth < tämä → pyöreä profiili
_MIN_INLIERS = 50
_MIN_HEIGHT_MM = 1500.0      # alle tämän → kalusteita, ei rakenteellinen pilari


class ColumnDetector(ElementDetector):
    """Löytää pilarit DBSCAN-klusteroinnilla."""

    def __init__(
        self,
        eps_mm: float = 80.0,       # DBSCAN-ympäristösäde
        min_points: int = 30,       # DBSCAN-minimipisteet
    ) -> None:
        self.eps_mm = eps_mm
        self.min_points = min_points

    def detect(
        self,
        cloud: o3d.geometry.PointCloud,
    ) -> tuple[list[Column], o3d.geometry.PointCloud]:
        pts = np.asarray(cloud.points)
        if len(pts) < self.min_points:
            return [], cloud

        # Isolla pilvellä DBSCAN on hidas (O(n) klusteria · naapurihaut): pilarit
        # ovat isoja pintapiirteitä, joten klusterointi tehdään karkeasti
        # harvennetusta kopiosta (~120k pistettä). Pilarin pinnat säilyvät, mutta
        # DBSCAN-kustannus romahtaa.
        from .wall_detector import _downsample_to_target
        if len(pts) > 120_000:
            work = _downsample_to_target(cloud, target=120_000, start_voxel=max(self.eps_mm * 0.7, 50.0))
            wpts = np.asarray(work.points)
        else:
            wpts = pts

        wpts_xy = wpts.copy()
        wpts_xy[:, 2] = 0.0
        cloud_2d = o3d.geometry.PointCloud()
        cloud_2d.points = o3d.utility.Vector3dVector(wpts_xy)
        labels = np.asarray(cloud_2d.cluster_dbscan(
            eps=self.eps_mm,
            min_points=self.min_points,
            print_progress=False,
        ))

        columns: list[Column] = []
        footprints: list[tuple[float, float, float]] = []  # cx, cy, puolikas-leveys
        unique = set(labels.tolist())
        unique.discard(-1)

        for label in unique:
            cluster = wpts[labels == label]
            col = self._cluster_to_column(cluster, label)
            if col is not None:
                columns.append(col)
                half = max(col.profile.width, col.profile.depth) / 2.0 + self.eps_mm
                footprints.append((col.location[0], col.location[1], half))

        # Poista pilari-inlierit täysresoluutiosta XY-footprintilla (vektoroitu).
        if footprints:
            keep = np.ones(len(pts), dtype=bool)
            for cx, cy, half in footprints:
                inside = (np.abs(pts[:, 0] - cx) <= half) & (np.abs(pts[:, 1] - cy) <= half)
                keep &= ~inside
            remaining_pts = pts[keep]
        else:
            remaining_pts = pts

        remaining = o3d.geometry.PointCloud()
        remaining.points = o3d.utility.Vector3dVector(remaining_pts)

        log.info("ColumnDetector: %d pilaria, %d pistettä jäljellä",
                 len(columns), len(remaining_pts))
        return columns, remaining

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

"""Palkkidetektori: DBSCAN katto-vyöhykkeessä + pitkänomaiset klusterit.

Algoritmi:
  1. Rajataan pisteet lähelle kattoa (z > z_max - sub_ceiling_mm).
  2. DBSCAN XY-tasoon projisoituna (kuten ColumnDetector).
  3. Pitkänomaiset klusterit (aspekti ≥ min_aspect) → palkit.
  4. Akseli: PCA XY-tasossa → 3D-päätepisteet z-keskiarvolla.
"""
from __future__ import annotations

import uuid
import logging

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import Beam, BeamProfile, ElementSource
from .base import ElementDetector

log = logging.getLogger(__name__)

_MIN_INLIERS = 30
_MIN_ASPECT = 3.0          # length/width — alle tämän = pilari, ei palkki
_MIN_LENGTH_MM = 400.0
_MAX_WIDTH_MM = 600.0      # palkin max-leveys (ei katto/laatta)
_MIN_HEIGHT_MM = 50.0      # palkin min-z-ulottuvuus (depth)


class BeamDetector(ElementDetector):
    """Löytää palkit kattovyöhykkeen pitkänomaisista klustereista."""

    def __init__(
        self,
        sub_ceiling_mm: float = 700.0,   # kuinka syvältä katosta etsitään
        eps_mm: float = 80.0,
        min_points: int = 20,
    ) -> None:
        self.sub_ceiling_mm = sub_ceiling_mm
        self.eps_mm = eps_mm
        self.min_points = min_points

    def detect(self, cloud: o3d.geometry.PointCloud) -> list[Beam]:
        pts = np.asarray(cloud.points)
        if len(pts) < self.min_points:
            return []

        z_max = float(pts[:, 2].max())
        z_lo = z_max - self.sub_ceiling_mm
        z_hi = z_max - 30.0    # jätetään kattopinnan pisteet pois

        mask = (pts[:, 2] >= z_lo) & (pts[:, 2] < z_hi)
        zone_pts = pts[mask]

        if len(zone_pts) < self.min_points:
            return []

        # DBSCAN XY
        zone_2d = zone_pts.copy()
        zone_2d[:, 2] = 0.0
        cloud_2d = o3d.geometry.PointCloud()
        cloud_2d.points = o3d.utility.Vector3dVector(zone_2d)
        labels = np.asarray(cloud_2d.cluster_dbscan(
            eps=self.eps_mm,
            min_points=self.min_points,
            print_progress=False,
        ))

        beams: list[Beam] = []
        for label in set(labels.tolist()):
            if label == -1:
                continue
            cluster = zone_pts[labels == label]
            beam = self._cluster_to_beam(cluster, label)
            if beam is not None:
                beams.append(beam)

        log.info("BeamDetector: %d palkkia löytyi katto-vyöhykkeestä (z≥%.0f)", len(beams), z_lo)
        return beams

    # ------------------------------------------------------------------ #

    def _cluster_to_beam(self, pts: np.ndarray, label: int) -> Beam | None:
        if len(pts) < _MIN_INLIERS:
            return None

        xy = pts[:, :2]
        center_xy = xy.mean(axis=0)
        cov = np.cov((xy - center_xy).T)
        _, eigvecs = np.linalg.eigh(cov)
        axis_dir = eigvecs[:, -1]

        proj = (xy - center_xy) @ axis_dir
        length = float(proj.max() - proj.min())
        if length < _MIN_LENGTH_MM:
            return None

        perp = eigvecs[:, 0]
        width = float(((xy - center_xy) @ perp).ptp())
        if width > _MAX_WIDTH_MM or width < 10:
            return None

        if length / (width + 1e-6) < _MIN_ASPECT:
            return None

        z_depth = float(pts[:, 2].ptp())
        if z_depth < _MIN_HEIGHT_MM:
            return None

        # Päätepisteet
        p0_xy = center_xy + proj.min() * axis_dir
        p1_xy = center_xy + proj.max() * axis_dir
        z_mid = float(pts[:, 2].mean())

        profile = BeamProfile(width=round(width, 1), height=round(z_depth, 1))
        confidence = round(min(1.0, len(pts) / 1500.0), 3)

        return Beam(
            id=str(uuid.uuid4()),
            confidence=confidence,
            source=ElementSource(method="cluster", plane_ids=[label]),
            axis=[
                [round(float(p0_xy[0]), 1), round(float(p0_xy[1]), 1), round(z_mid, 1)],
                [round(float(p1_xy[0]), 1), round(float(p1_xy[1]), 1), round(z_mid, 1)],
            ],
            profile=profile,
        )

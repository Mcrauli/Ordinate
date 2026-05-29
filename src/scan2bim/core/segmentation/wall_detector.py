"""RANSAC-pohjainen seinädetektori.

Algoritmi:
  1. Etsii tasot RANSAC:lla iteratiivisesti (jäljellä olevasta pilvestä).
  2. Suodattaa vertikaaliset tasot (|normal_z| < threshold).
  3. Yhdistää rinnakkaiset vastaavat tasot pariksi → paksuus.
  4. Poimii akselin PCA:lla, laskee korkeus z-vaihteluvälistä.
"""
from __future__ import annotations

import uuid
import logging

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import Wall, ElementSource
from .base import ElementDetector

log = logging.getLogger(__name__)

# --- Kynnysarvot --------------------------------------------------------- #
_VERTICAL_NORMAL_Z_MAX = 0.20   # |n_z| < tämä → vertikaalinen taso (seinä)
_MIN_INLIERS = 300              # alle tämän → ei seinä
_MIN_LENGTH_MM = 200.0          # min seinäpituus
_MIN_HEIGHT_MM = 400.0          # min seinäkorkeus
_THICKNESS_MIN_MM = 50.0        # min järkevä paksuus
_THICKNESS_MAX_MM = 900.0       # max järkevä paksuus
_PARALLEL_CROSS_MAX = 0.10      # cross-product normaaleille — alle = rinnakkaiset
_DEFAULT_THICKNESS_MM = 200.0   # fallback jos paria ei löydy


class WallDetector(ElementDetector):
    """Löytää seinät pistepilvestä RANSAC-tasosegmentoinnin avulla."""

    def __init__(
        self,
        distance_threshold: float = 25.0,   # mm — inlier-etäisyys tasosta
        ransac_n: int = 3,
        num_iterations: int = 1000,
        max_planes: int = 30,
    ) -> None:
        self.distance_threshold = distance_threshold
        self.ransac_n = ransac_n
        self.num_iterations = num_iterations
        self.max_planes = max_planes

    def detect(self, cloud: o3d.geometry.PointCloud) -> list[Wall]:
        planes = self._extract_planes(cloud)
        log.info("Löytyi %d tasoa, joista vertikaalia: %d",
                 len(planes),
                 sum(1 for p in planes if abs(p["normal"][2]) < _VERTICAL_NORMAL_Z_MAX))

        vertical = [p for p in planes if abs(p["normal"][2]) < _VERTICAL_NORMAL_Z_MAX]

        walls: list[Wall] = []
        used: set[int] = set()

        for i, plane in enumerate(vertical):
            if i in used:
                continue
            partner_idx, thickness = self._find_partner(i, vertical)
            if partner_idx is not None:
                used.add(partner_idx)
            wall = self._plane_to_wall(plane, thickness, paired=(partner_idx is not None))
            if wall is not None:
                walls.append(wall)

        log.info("WallDetector: %d seinää löytyi", len(walls))
        return walls

    # ------------------------------------------------------------------ #
    # Yksityiset apumetodit
    # ------------------------------------------------------------------ #

    def _extract_planes(self, cloud: o3d.geometry.PointCloud) -> list[dict]:
        remaining = cloud
        planes: list[dict] = []

        for plane_id in range(self.max_planes):
            if len(remaining.points) < max(self.ransac_n, _MIN_INLIERS):
                break
            eq, inliers = remaining.segment_plane(
                distance_threshold=self.distance_threshold,
                ransac_n=self.ransac_n,
                num_iterations=self.num_iterations,
            )
            if len(inliers) < _MIN_INLIERS:
                break
            normal = np.array(eq[:3])
            norm_len = np.linalg.norm(normal)
            if norm_len > 0:
                normal /= norm_len
            planes.append({
                "id": plane_id,
                "normal": normal,
                "d": float(eq[3]) / (norm_len if norm_len > 0 else 1.0),
                "cloud": remaining.select_by_index(inliers),
            })
            remaining = remaining.select_by_index(inliers, invert=True)

        return planes

    def _find_partner(self, i: int, planes: list[dict]) -> tuple[int | None, float]:
        """Etsii rinnakkaisen vastakkaisen tason (toinen seinäpinta). Palauttaa (indeksi, paksuus)."""
        p = planes[i]
        best_idx: int | None = None
        best_dist: float | None = None

        for j, q in enumerate(planes):
            if j == i:
                continue
            cross = float(np.linalg.norm(np.cross(p["normal"], q["normal"])))
            if cross > _PARALLEL_CROSS_MAX:
                continue
            dist = abs(p["d"] - q["d"])
            if dist < _THICKNESS_MIN_MM or dist > _THICKNESS_MAX_MM:
                continue
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = j

        return best_idx, (best_dist if best_dist is not None else _DEFAULT_THICKNESS_MM)

    def _plane_to_wall(self, plane: dict, thickness: float, paired: bool) -> Wall | None:
        pts = np.asarray(plane["cloud"].points)
        if len(pts) < _MIN_INLIERS:
            return None

        # Akseli: PCA XY-tasoon projisoituna
        xy = pts[:, :2]
        center_xy = xy.mean(axis=0)
        cov = np.cov((xy - center_xy).T)
        _, eigvecs = np.linalg.eigh(cov)
        axis_dir = eigvecs[:, -1]   # suurin ominaisarvo = pituussuunta

        proj = (xy - center_xy) @ axis_dir
        p0_xy = center_xy + proj.min() * axis_dir
        p1_xy = center_xy + proj.max() * axis_dir
        length = float(np.linalg.norm(p1_xy - p0_xy))

        if length < _MIN_LENGTH_MM:
            return None

        height = float(pts[:, 2].max() - pts[:, 2].min())
        if height < _MIN_HEIGHT_MM:
            return None

        # Confidence: enemmän inliirejä + pari löytyi → korkeampi
        raw_conf = min(1.0, len(pts) / 8000.0)
        confidence = round(raw_conf * (0.95 if paired else 0.65), 3)

        return Wall(
            id=str(uuid.uuid4()),
            confidence=confidence,
            source=ElementSource(method="ransac", plane_ids=[plane["id"]]),
            axis=[[float(p0_xy[0]), float(p0_xy[1])],
                  [float(p1_xy[0]), float(p1_xy[1])]],
            height=round(height, 1),
            thickness=round(thickness, 1),
        )

"""RANSAC-pohjainen seinädetektori.

Algoritmi:
  1. Etsii tasot RANSAC:lla iteratiivisesti (jäljellä olevasta pilvestä).
  2. Suodattaa vertikaaliset tasot (|normal_z| < threshold).
  3. Yhdistää rinnakkaiset vastaavat tasot pariksi → paksuus.
  4. Poimii akselin PCA:lla, laskee korkeus z-vaihteluvälistä.

Palauttaa (walls, remaining_cloud) — remaining on pilvi ilman seinä-inliereita.
Lattia/katto-inliereitä EI poisteta, jotta SlabDetector löytää ne.
"""
from __future__ import annotations

import uuid
import logging

import numpy as np
import open3d as o3d

from ordinate.schemas.model import Wall, ElementSource
from .base import ElementDetector

log = logging.getLogger(__name__)


def _downsample_to_target(
    cloud: o3d.geometry.PointCloud,
    target: int,
    start_voxel: float,
    max_voxel: float = 250.0,
) -> o3d.geometry.PointCloud:
    """Harvenna pilvi karkeasti ~target pisteeseen (kasvattaen voxelia).
    Käytetään raskaisiin geometriavaiheisiin; täysi pilvi säilyy kutsujalla."""
    if len(cloud.points) <= target:
        return cloud
    voxel = start_voxel
    work = cloud.voxel_down_sample(voxel)
    while len(work.points) > target and voxel < max_voxel:
        voxel *= 1.5
        work = cloud.voxel_down_sample(voxel)
    return work


_VERTICAL_NORMAL_Z_MAX = 0.20
_MIN_INLIERS = 300
_MIN_LENGTH_MM = 200.0
_MIN_HEIGHT_MM = 400.0
_THICKNESS_MIN_MM = 50.0
_THICKNESS_MAX_MM = 900.0
_PARALLEL_CROSS_MAX = 0.10
_DEFAULT_THICKNESS_MM = 200.0
_WALL_BIN_MM = 150.0          # seinäakselin segmentoinnin rasterointi
_WALL_GAP_MM = 800.0          # tätä pidempi tyhjä jakso katkaisee seinän


class WallDetector(ElementDetector):
    """Löytää seinät RANSAC-tasosegmentoinnilla."""

    def __init__(
        self,
        distance_threshold: float = 25.0,
        ransac_n: int = 3,
        num_iterations: int = 1000,
        max_planes: int = 30,
    ) -> None:
        self.distance_threshold = distance_threshold
        self.ransac_n = ransac_n
        self.num_iterations = num_iterations
        self.max_planes = max_planes

    def detect(
        self,
        cloud: o3d.geometry.PointCloud,
    ) -> tuple[list[Wall], o3d.geometry.PointCloud]:
        # Tasogeometria ei tarvitse täyttä resoluutiota: iso pilvi tekee
        # RANSACista (30 × segment_plane) minuuttien mittaisen. Haetaan tasot
        # harvennetusta kopiosta ja vähennetään inlierit silti TÄYDESTÄ pilvestä.
        work = _downsample_to_target(cloud, target=400_000, start_voxel=30.0)
        planes = self._extract_planes(work)

        vertical = [p for p in planes if abs(p["normal"][2]) < _VERTICAL_NORMAL_Z_MAX]
        log.info("Löytyi %d tasoa, vertikaalia: %d", len(planes), len(vertical))

        walls: list[Wall] = []
        used: set[int] = set()

        for i, plane in enumerate(vertical):
            if i in used:
                continue
            partner_idx, thickness = self._find_partner(i, vertical)
            if partner_idx is not None:
                used.add(partner_idx)
            walls.extend(self._plane_to_walls(plane, thickness, paired=(partner_idx is not None)))

        # Poista VAIN vertikaaliset (seinä)tasot — lattia/katto jätetään
        remaining = self._subtract_planes(cloud, vertical)

        log.info("WallDetector: %d seinää, %d pistettä jäljellä",
                 len(walls), len(remaining.points))
        return walls, remaining

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
            norm_len = float(np.linalg.norm(normal))
            if norm_len > 0:
                normal = normal / norm_len
            planes.append({
                "id": plane_id,
                "normal": normal,
                "d": float(eq[3]) / (norm_len if norm_len > 0 else 1.0),
                "eq": np.array(eq),
                "cloud": remaining.select_by_index(inliers),
            })
            remaining = remaining.select_by_index(inliers, invert=True)
        return planes

    def _subtract_planes(
        self,
        cloud: o3d.geometry.PointCloud,
        planes: list[dict],
    ) -> o3d.geometry.PointCloud:
        """Poistaa tiettyjen tasojen inlier-pisteet alkuperäisestä pilvestä."""
        if not planes:
            return cloud
        orig_pts = np.asarray(cloud.points)
        keep = np.ones(len(orig_pts), dtype=bool)
        for p in planes:
            n = p["normal"]
            d = p["d"]
            dists = np.abs(orig_pts @ n + d)
            keep &= dists > self.distance_threshold
        result = o3d.geometry.PointCloud()
        result.points = o3d.utility.Vector3dVector(orig_pts[keep])
        return result

    def _find_partner(self, i: int, planes: list[dict]) -> tuple[int | None, float]:
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

    def _plane_to_walls(self, plane: dict, thickness: float, paired: bool) -> list[Wall]:
        """Pilko taso todellisiksi seinänpätkiksi.

        Yksi RANSAC-taso on ääretön — sen inlierit voivat osua useaan erilliseen
        seinään tai sisältää pitkiä tyhjiä jaksoja (taso leikkaa tilaa). Projisoidaan
        inlierit tason vaakasuuntaiselle akselille, etsitään tiheät yhtenäiset
        jaksot (>_WALL_GAP_MM tyhjä katkaisee) ja tehdään jokaisesta oma seinä.
        Näin 70 m "seinä" hajoaa oikeiksi seiniksi."""
        pts = np.asarray(plane["cloud"].points)
        if len(pts) < _MIN_INLIERS:
            return []
        xy = pts[:, :2]
        center_xy = xy.mean(axis=0)
        cov = np.cov((xy - center_xy).T)
        _, eigvecs = np.linalg.eigh(cov)
        axis_dir = eigvecs[:, -1]
        proj = (xy - center_xy) @ axis_dir

        lo, hi = float(proj.min()), float(proj.max())
        nb = max(int((hi - lo) / _WALL_BIN_MM) + 1, 1)
        counts, edges = np.histogram(proj, bins=nb, range=(lo, hi))
        nz = counts[counts > 0]
        if len(nz) == 0:
            return []
        occ_thr = max(2.0, 0.12 * float(np.median(nz)))
        occ = counts >= occ_thr

        notes = "thickness_measured" if paired else "thickness_default"
        gap_bins = max(int(_WALL_GAP_MM / _WALL_BIN_MM), 1)

        walls: list[Wall] = []
        i = 0
        while i < nb:
            if not occ[i]:
                i += 1
                continue
            j = i
            gap = 0
            last = i
            while j < nb:
                if occ[j]:
                    last = j
                    gap = 0
                else:
                    gap += 1
                    if gap > gap_bins:
                        break
                j += 1
            a = float(edges[i])
            b = float(edges[last + 1])
            i = j

            seg_mask = (proj >= a) & (proj <= b)
            seg = pts[seg_mask]
            if len(seg) < _MIN_INLIERS:
                continue
            length = b - a
            if length < _MIN_LENGTH_MM:
                continue
            height = float(seg[:, 2].max() - seg[:, 2].min())
            if height < _MIN_HEIGHT_MM:
                continue
            p0_xy = center_xy + a * axis_dir
            p1_xy = center_xy + b * axis_dir
            raw_conf = min(1.0, len(seg) / 4000.0)
            confidence = round(raw_conf * (0.95 if paired else 0.65), 3)
            walls.append(Wall(
                id=str(uuid.uuid4()),
                confidence=confidence,
                source=ElementSource(method="ransac", plane_ids=[plane["id"]], notes=notes),
                axis=[[float(p0_xy[0]), float(p0_xy[1])],
                      [float(p1_xy[0]), float(p1_xy[1])]],
                height=round(height, 1),
                thickness=round(thickness, 1),
                z_min=round(float(seg[:, 2].min()), 1),
            ))
        return walls

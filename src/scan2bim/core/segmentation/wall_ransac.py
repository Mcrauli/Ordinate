"""Seinädetektio iteratiivisella RANSAC-tasosegmentoinnilla. Sisään: o3d.PointCloud → ulos: StructuralModel."""
from __future__ import annotations

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import ElementSource, Metadata, StructuralModel, Wall

from .base import DetectorRegistry, ElementDetector

_VERTICAL_NZ_MAX = 0.25     # |nz| < 0.25 → seinätaso
_MIN_WALL_HEIGHT = 1500.0   # mm
_MIN_PLANE_PTS = 150
_RANSAC_DIST = 3.0          # mm
_MAX_PLANES = 50
_PARALLEL_DEG = 12.0        # normaalikulma saman suuntaisille tasoille
_MAX_THICKNESS = 500.0      # mm


@DetectorRegistry.register("ransac")
class WallDetectorRANSAC(ElementDetector):
    def __init__(
        self,
        ransac_distance: float = _RANSAC_DIST,
        min_wall_height: float = _MIN_WALL_HEIGHT,
        min_plane_points: int = _MIN_PLANE_PTS,
        max_planes: int = _MAX_PLANES,
    ) -> None:
        self.ransac_distance = ransac_distance
        self.min_wall_height = min_wall_height
        self.min_plane_points = min_plane_points
        self.max_planes = max_planes

    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        planes = self._extract_planes(cloud)
        walls = self._planes_to_walls(planes, len(cloud.points))
        model = StructuralModel(walls=walls)
        model.metadata = Metadata(detector_method="ransac")
        return model

    def _extract_planes(self, cloud: o3d.geometry.PointCloud) -> list[tuple]:
        remaining = cloud
        planes: list[tuple] = []

        for _ in range(self.max_planes):
            if len(remaining.points) < self.min_plane_points:
                break
            plane_model, inliers = remaining.segment_plane(
                distance_threshold=self.ransac_distance,
                ransac_n=3,
                num_iterations=1000,
            )
            if len(inliers) < self.min_plane_points:
                break

            pts = np.asarray(remaining.select_by_index(inliers).points)
            z_extent = pts[:, 2].max() - pts[:, 2].min()
            a, b, c, _ = plane_model
            norm = np.sqrt(a**2 + b**2 + c**2)
            nz = abs(c / norm) if norm > 0 else 1.0

            if nz < _VERTICAL_NZ_MAX and z_extent >= self.min_wall_height:
                planes.append((plane_model, pts))

            remaining = remaining.select_by_index(inliers, invert=True)

        return planes

    def _planes_to_walls(self, planes: list[tuple], total_pts: int) -> list[Wall]:
        walls: list[Wall] = []
        used = [False] * len(planes)

        for i, (model_i, pts_i) in enumerate(planes):
            if used[i]:
                continue

            a_i, b_i, c_i, d_i = model_i
            ni = np.array([a_i, b_i, c_i], dtype=float)
            ni /= np.linalg.norm(ni)

            thickness = 200.0
            paired_ids: list[int] = [i]

            for j in range(i + 1, len(planes)):
                if used[j]:
                    continue
                a_j, b_j, c_j, d_j = planes[j][0]
                nj = np.array([a_j, b_j, c_j], dtype=float)
                nj /= np.linalg.norm(nj)

                signed_dot = float(np.dot(ni, nj))
                angle_deg = float(np.degrees(np.arccos(np.clip(abs(signed_dot), 0.0, 1.0))))
                if angle_deg > _PARALLEL_DEG:
                    continue

                dist = abs(d_i - d_j * (1.0 if signed_dot > 0 else -1.0))
                if dist < _MAX_THICKNESS:
                    thickness = float(dist)
                    paired_ids.append(j)
                    used[j] = True
                    break

            axis, height, coverage = _plane_to_axis(pts_i)
            # Koko-suhteinen conf aliarvioi ISON skenen sisäseinät: iso myymälä on
            # niin pinta-alaltaan suuri, että 12 m takahuoneen seinä on murto-osa
            # koko pilvestä → conf ~0.01 → filtteri pudottaa aidon seinän. Peitto
            # (occupancy tiheintä jännettä pitkin) on skaalariippumaton: aito seinä
            # on tiheästi katettu pituudeltaan, kontaminoitunut hajanne ei. Otetaan
            # suurempi → nostaa vain, ei laske (monotoninen, ei pudota mitään).
            size_conf = min(1.0, len(pts_i) / max(total_pts * 0.05, 1))
            confidence = max(size_conf, coverage)
            z_min = float(pts_i[:, 2].min())

            walls.append(Wall(
                id=f"wall_{i:03d}",
                confidence=round(confidence, 3),
                classification="wall",
                source=ElementSource(method="ransac", plane_ids=paired_ids),
                axis=axis,
                height=round(height, 1),
                thickness=round(thickness, 1),
                z_min=round(z_min, 1),
            ))
            used[i] = True

        return walls


_COVER_BIN_MM = 250.0       # mm — peittobinin leveys akselia pitkin
_COVER_MIN_BIN_PTS = 3      # bin "katettu" kun ≥ tämä pistettä
_COVER_GAP_BRIDGE_MM = 1600.0  # mm — tätä pienemmät aukot (ovet/ikkunat) sillataan
_COVER_MIN_SEG_MM = 2000.0  # mm — lyhyempi katettu jänne EI ole seinänäyttö; muuten
                            # yksittäinen pilari (~0.5 m täysin katettu) tai pilaririvi
                            # (jokainen pilari erillinen lyhyt jänne) saisi peiton 1.0


def _dense_segment(proj: np.ndarray) -> tuple[float, float, float]:
    """Tihein yhtäjaksoinen seinäjänne akselia pitkin.

    Palauttaa (peitto 0..1, t_lo, t_hi) missä t_lo/t_hi ovat projektioarvot
    (samassa origossa kuin ``proj``). Aito seinä on lähes yhtäjaksoisesti katettu
    (ovi/ikkuna-aukot sillataan); pilarilinjan tms. kontaminoima taso venyy
    pitkälle harvana → matala peitto JA väärä min–max-laajuus. Käytetään sekä
    confidencen (skaalariippumaton peitto) että akselin laajuuden (ei venytä
    kontaminaation ääripisteisiin) määrittämiseen."""
    lo, hi = float(proj.min()), float(proj.max())
    span = hi - lo
    if span < _COVER_BIN_MM:
        return 1.0, lo, hi
    nb = max(int(span / _COVER_BIN_MM), 1)
    hist, edges = np.histogram(proj, bins=nb, range=(lo, hi))
    occ = np.flatnonzero(hist >= _COVER_MIN_BIN_PTS)
    if occ.size == 0:
        return 0.0, lo, hi
    bin_mm = span / nb
    gap_bins = max(int(_COVER_GAP_BRIDGE_MM / bin_mm), 1)

    def _seg_cover(s, e):
        width = e - s + 1
        if width * bin_mm < _COVER_MIN_SEG_MM:
            return 0.0
        covered = int(np.count_nonzero((occ >= s) & (occ <= e)))
        return covered / width if width > 0 else 0.0

    # Ryhmittele katetut binit jänteiksi: > gap_bins peräkkäistä tyhjää katkaisee.
    # Paras = korkein peitto (tihein pitkä jänne), ja sen reunat rajaavat akselin.
    best_cov, best_s, best_e = 0.0, occ[0], occ[-1]
    start = prev = occ[0]
    for k in occ[1:]:
        if k - prev > gap_bins:
            c = _seg_cover(start, prev)
            if c > best_cov:
                best_cov, best_s, best_e = c, start, prev
            start = k
        prev = k
    c = _seg_cover(start, prev)
    if c > best_cov:
        best_cov, best_s, best_e = c, start, prev

    if best_cov <= 0.0:
        return 0.0, lo, hi   # ei aitoa jännettä → jätä laajuus ennalleen
    t_lo = float(edges[best_s])
    t_hi = float(edges[best_e + 1])
    return float(min(1.0, best_cov)), t_lo, t_hi


def _plane_to_axis(pts: np.ndarray) -> tuple[list[list[float]], float, float]:
    xy = pts[:, :2]
    centroid = xy.mean(axis=0)
    _, _, vt = np.linalg.svd(xy - centroid, full_matrices=False)
    direction = vt[0]
    proj = (xy - centroid) @ direction
    half = (proj.max() - proj.min()) / 2.0
    p0 = centroid - half * direction
    p1 = centroid + half * direction
    height = float(pts[:, 2].max() - pts[:, 2].min())
    coverage, _, _ = _dense_segment(proj)
    return (
        [[round(float(p0[0]), 1), round(float(p0[1]), 1)],
         [round(float(p1[0]), 1), round(float(p1[1]), 1)]],
        height,
        coverage,
    )

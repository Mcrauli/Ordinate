"""Z-histogram-pohjainen laattadetektori (lattia / katto).

Algoritmi:
  1. Z-histogrammi koko pilvestä → löytää tiheät vaakatasot.
  2. Jokaisesta piikin ympäristöstä poimitaan pisteet.
  3. Konveksi peite XY-tasossa → laatan raja.
  4. Luokittelu: alin taso = lattia, ylin = katto, välissä olevat = lattia (välipohjat).
"""
from __future__ import annotations

import uuid
import logging

import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull

from scan2bim.schemas.model import Slab, ElementSource
from .base import ElementDetector

log = logging.getLogger(__name__)

_MIN_INLIERS = 400
_MIN_HULL_VERTS = 3


class SlabDetector(ElementDetector):
    """Tunnistaa lattiat ja katot z-histogrammista."""

    def __init__(
        self,
        z_bin_mm: float = 30.0,        # histogrammibiinin leveys
        peak_min_fraction: float = 0.04, # piikin minimiprosentti pisteiden kokonaismäärästä
        z_band_mm: float = 45.0,        # kaista piikin ympärillä pisteiden poimintaan
        slab_thickness_mm: float = 150.0,
        min_area_mm2: float = 200_000,  # ~0.2 m² — pienempi suodatetaan pois
    ) -> None:
        self.z_bin_mm = z_bin_mm
        self.peak_min_fraction = peak_min_fraction
        self.z_band_mm = z_band_mm
        self.slab_thickness_mm = slab_thickness_mm
        self.min_area_mm2 = min_area_mm2

    def detect(self, cloud: o3d.geometry.PointCloud) -> list[Slab]:
        pts = np.asarray(cloud.points)
        if len(pts) < _MIN_INLIERS:
            return []

        z = pts[:, 2]
        z_min, z_max = float(z.min()), float(z.max())
        n_bins = max(10, int((z_max - z_min) / self.z_bin_mm))

        hist, edges = np.histogram(z, bins=n_bins)
        bin_centers = (edges[:-1] + edges[1:]) / 2

        min_count = len(pts) * self.peak_min_fraction
        peak_bins = self._find_peaks(hist, min_count)

        if not peak_bins:
            log.info("SlabDetector: ei tarpeeksi selkeitä vaakatasoja")
            return []

        peak_z = sorted(bin_centers[i] for i in peak_bins)
        log.info("SlabDetector: %d vaakatasoa z=%s", len(peak_z),
                 [f"{v:.0f}" for v in peak_z])

        slabs: list[Slab] = []
        n_peaks = len(peak_z)

        for j, z_center in enumerate(peak_z):
            if j == 0:
                slab_type = "floor"
            elif j == n_peaks - 1:
                slab_type = "ceiling"
            else:
                slab_type = "floor"   # välipohjat → floor

            mask = np.abs(z - z_center) <= self.z_band_mm
            inliers = pts[mask]
            if len(inliers) < _MIN_INLIERS:
                continue

            boundary = self._convex_hull_xy(inliers[:, :2])
            if boundary is None:
                continue

            area = self._polygon_area(boundary)
            if area < self.min_area_mm2:
                continue

            conf = round(min(1.0, len(inliers) / 25_000.0), 3)
            slabs.append(
                Slab(
                    id=str(uuid.uuid4()),
                    confidence=conf,
                    source=ElementSource(method="z_histogram"),
                    slab_type=slab_type,
                    boundary=boundary,
                    elevation=round(float(z_center), 1),
                    thickness=self.slab_thickness_mm,
                )
            )

        log.info("SlabDetector: %d laattaa löytyi", len(slabs))
        return slabs

    # ------------------------------------------------------------------ #

    def _find_peaks(self, hist: np.ndarray, min_count: float) -> list[int]:
        """Paikallisia maksimeja, joilla tarpeeksi pisteitä. Yhdistää vierekkäiset.

        Reunabiinit (i=0 ja i=n-1) voivat myös olla piikkejä — lattia/katto
        ovat usein z-alueen reunoilla normalisoinnin jälkeen.
        """
        n = len(hist)
        raw: list[int] = []
        for i in range(n):
            if hist[i] < min_count:
                continue
            left = hist[i - 1] if i > 0 else 0
            right = hist[i + 1] if i < n - 1 else 0
            if hist[i] >= left and hist[i] >= right:
                raw.append(i)

        if len(raw) < 2:
            return raw

        # Yhdistä max 2 biiniä etäisyydellä olevat piikki → korkeampi voittaa
        merged: list[int] = [raw[0]]
        for idx in raw[1:]:
            if idx - merged[-1] <= 2:
                if hist[idx] > hist[merged[-1]]:
                    merged[-1] = idx
            else:
                merged.append(idx)
        return merged

    def _convex_hull_xy(self, xy: np.ndarray) -> list[list[float]] | None:
        if len(xy) < _MIN_HULL_VERTS:
            return None
        try:
            hull = ConvexHull(xy)
            verts = xy[hull.vertices]
            poly = [[float(x), float(y)] for x, y in verts]
            poly.append(poly[0])   # suljettu polygoni
            return poly
        except Exception:
            return None

    @staticmethod
    def _polygon_area(poly: list[list[float]]) -> float:
        """Shoelace-kaava."""
        n = len(poly) - 1   # viimeinen == ensimmäinen
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += poly[i][0] * poly[j][1]
            area -= poly[j][0] * poly[i][1]
        return abs(area) / 2.0

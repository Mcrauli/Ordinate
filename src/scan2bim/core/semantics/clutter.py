"""Krääsäsuodatus: pisteet jotka eivät kuulu rakenteisiin → Discarded.

Strategia:
  1. Lasketaan kuinka monta pistettä eri detektorit "käyttivät" (inliers).
  2. Jäljelle jäävät pisteet klusteroidaan DBSCAN:lla.
  3. Klusterit joilla pieni footprint (< seinä) ja matalat (< seinäkorkeus)
     → krääsää (kalusteet, LVI, ihmiset).
  4. Päivitetään StructuralModel.discarded-kenttä.

Tämä on best-effort — pisteet eivät konkreettisesti poistu pilvestä ennen
segmentointia, vaan kirjaamme vain loput klusterit läpinäkyvyyden vuoksi.
"""
from __future__ import annotations

import logging

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import StructuralModel, Discarded

log = logging.getLogger(__name__)

_CLUTTER_MAX_HEIGHT = 1800.0   # mm — yläpuolella oleva voi olla rakenne
_CLUTTER_MAX_FOOTPRINT = 2000.0  # mm — pienempää kuin tämä
_MIN_CLUTTER_PTS = 50


def detect_clutter(
    cloud: o3d.geometry.PointCloud,
    model: StructuralModel,
    eps_mm: float = 100.0,
    min_points: int = 30,
) -> Discarded:
    """Klusteroi jäljellä olevat pisteet, laskee krääsäklusterit."""
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return Discarded()

    # Kaikki "käytetyt" pisteet ovat jo seinissä/latoissa/pilareissa.
    # Yksinkertainen aprox: jätä pois pisteet jotka ovat lähellä seinäakseleita
    # tai laatta/tilan tasoa. Tässä versiossa käytämme vain heuristiikkaa:
    # DBSCAN koko pilvellä → klusterit joiden ulottuvuus on kaluste-kokoinen.

    pts_2d = pts.copy()
    pts_2d[:, 2] = 0.0
    cloud_2d = o3d.geometry.PointCloud()
    cloud_2d.points = o3d.utility.Vector3dVector(pts_2d)
    labels = np.asarray(cloud_2d.cluster_dbscan(
        eps=eps_mm, min_points=min_points, print_progress=False,
    ))

    clutter_count = 0
    clutter_pts = 0

    for label in set(labels.tolist()):
        if label == -1:
            continue
        cluster = pts[labels == label]
        if len(cluster) < _MIN_CLUTTER_PTS:
            continue

        xy_span = np.ptp(cluster[:, :2], axis=0)
        z_span = float(cluster[:, 2].ptp())
        max_xy = float(xy_span.max())

        if max_xy < _CLUTTER_MAX_FOOTPRINT and z_span < _CLUTTER_MAX_HEIGHT:
            # Tarkista ettei ole jo löydetty elementti (wall/column sijainnissa)
            center_xy = cluster[:, :2].mean(axis=0)
            if not _is_near_structure(center_xy, model):
                clutter_count += 1
                clutter_pts += len(cluster)

    log.info(
        "ClutterFilter: %d klusteria (%d pistettä) merkitty krääsäksi",
        clutter_count, clutter_pts,
    )
    return Discarded(
        clutter_cluster_count=clutter_count,
        total_points=clutter_pts,
        reason="furniture/MEP filtered by rule-based clutter detection",
    )


def _is_near_structure(center_xy: np.ndarray, model: StructuralModel, tol: float = 400.0) -> bool:
    """Palauttaa True jos piste on lähellä tunnettua rakenne-elementtiä."""
    for col in model.columns:
        loc = np.array(col.location)
        if float(np.linalg.norm(center_xy - loc)) < tol:
            return True
    for wall in model.walls:
        p0 = np.array(wall.axis[0])
        p1 = np.array(wall.axis[1])
        # Etäisyys pisteestä janolle
        seg = p1 - p0
        t = np.clip(np.dot(center_xy - p0, seg) / (np.dot(seg, seg) + 1e-9), 0, 1)
        closest = p0 + t * seg
        if float(np.linalg.norm(center_xy - closest)) < tol:
            return True
    return False

"""Pilaridetektio: pystysuuntaiset, seinistä irralliset pistekasaumat.

Algoritmi:
  1. Poista seinien lähipisteet (jää vapaasti seisovat rakenteet)
  2. Rajaa keskikorkeuden kaistaan (pois lattia/katto)
  3. DBSCAN-klusterointi XY:ssä
  4. Klusteri = pilari jos pieni XY-jalanjälki + ulottuu lähes lattiasta kattoon
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import Column, ColumnProfile, ElementSource, Wall

_WALL_MARGIN = 120.0       # mm — tätä lähempänä seinää = seinäpiste, ohitetaan
_Z_MARGIN = 300.0          # mm — lattia/katto-vyöhyke pois
_MAX_FOOTPRINT = 700.0     # mm — pilarin max XY-mitta
_MIN_FOOTPRINT = 80.0      # mm
_MIN_HEIGHT_FRAC = 0.55    # ulotuttava vähintään tämä osuus huonekorkeudesta
_DBSCAN_EPS = 150.0        # mm
_DBSCAN_MIN_PTS = 40
_MIN_CLUSTER_PTS = 120


def detect_columns(cloud, walls: list[Wall], floor_z: float, ceiling_z: float) -> list[Column]:
    pts = np.asarray(cloud.points)
    if len(pts) < _MIN_CLUSTER_PTS:
        return []

    room_h = ceiling_z - floor_z
    if room_h < 1500.0:
        return []

    # Keskikorkeuden kaista
    zmask = (pts[:, 2] > floor_z + _Z_MARGIN) & (pts[:, 2] < ceiling_z - _Z_MARGIN)
    band = pts[zmask]
    if len(band) < _MIN_CLUSTER_PTS:
        return []

    # Poista seinien lähipisteet
    far = _dist_to_walls(band[:, :2], walls) > _WALL_MARGIN
    free = band[far]
    if len(free) < _MIN_CLUSTER_PTS:
        return []

    sub = o3d.geometry.PointCloud()
    sub.points = o3d.utility.Vector3dVector(free)
    labels = np.asarray(sub.cluster_dbscan(eps=_DBSCAN_EPS, min_points=_DBSCAN_MIN_PTS))

    columns: list[Column] = []
    for lab in range(labels.max() + 1):
        cl = free[labels == lab]
        if len(cl) < _MIN_CLUSTER_PTS:
            continue
        xy = cl[:, :2]
        wx = float(xy[:, 0].max() - xy[:, 0].min())
        wy = float(xy[:, 1].max() - xy[:, 1].min())
        footprint = max(wx, wy)
        if not (_MIN_FOOTPRINT <= footprint <= _MAX_FOOTPRINT):
            continue

        z_extent = float(cl[:, 2].max() - cl[:, 2].min())
        if z_extent < _MIN_HEIGHT_FRAC * room_h:
            continue

        cx = float(xy[:, 0].mean())
        cy = float(xy[:, 1].mean())
        shape, w, d = _profile(xy, cx, cy, wx, wy)

        columns.append(Column(
            id=f"column_{len(columns):03d}",
            confidence=round(min(1.0, len(cl) / 600.0), 3),
            classification="column",
            source=ElementSource(method="cluster"),
            location=[round(cx, 1), round(cy, 1)],
            base_z=round(floor_z, 1),
            height=round(min(z_extent + 2 * _Z_MARGIN, room_h), 1),
            profile=ColumnProfile(shape=shape, width=round(w, 1), depth=round(d, 1)),
        ))

    return columns


def _profile(xy: np.ndarray, cx: float, cy: float, wx: float, wy: float):
    """Pyöreä jos pisteet ovat tasaisella säteellä, muuten suorakaide."""
    r = np.hypot(xy[:, 0] - cx, xy[:, 1] - cy)
    r_mean = float(r.mean())
    if r_mean > 1e-6 and float(r.std()) / r_mean < 0.20 and abs(wx - wy) < 0.3 * max(wx, wy):
        diam = 2.0 * r_mean
        return "circle", diam, diam
    return "rect", wx, wy


def _dist_to_walls(xy: np.ndarray, walls: list[Wall]) -> np.ndarray:
    """Pisteiden min-etäisyys seinäpintaan XY:ssä (akseli miinus puolipaksuus)."""
    if not walls:
        return np.full(len(xy), np.inf)
    dmin = np.full(len(xy), np.inf)
    for w in walls:
        if len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], dtype=float)
        p1 = np.array(w.axis[1], dtype=float)
        seg = p1 - p0
        L2 = float(seg @ seg)
        if L2 < 1.0:
            continue
        t = np.clip(((xy - p0) @ seg) / L2, 0.0, 1.0)
        proj = p0[None, :] + t[:, None] * seg[None, :]
        d = np.linalg.norm(xy - proj, axis=1) - w.thickness / 2.0
        dmin = np.minimum(dmin, d)
    return dmin

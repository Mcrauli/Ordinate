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


_CELL_MM = 100.0           # XY-ruudukon solu
_ZBIN_MM = 200.0           # pystypeiton binikoko
_VFILL_MIN = 0.70          # solun pystytäyttö ≥ tämä → pilariehdokas
_COMP_MIN_MM = 180.0       # komponentin min-mitta (holvituki ~70mm putoaa)
_COMP_MAX_MM = 800.0       # komponentin max-mitta
_RING_IN = 2               # rengas alkaa (soluja bboxin reunasta)
_RING_OUT = 6              # rengas päättyy
_RING_MAX_CELLS = 6        # renkaassa saa olla korkeintaan näin monta täyttösolua
_MIN_ABS_HEIGHT = 2300.0   # mm — monitasoscenessä room_h vääristyy; aito pilari ≥ tämä


def detect_columns(cloud, walls: list[Wall], floor_z: float, ceiling_z: float) -> list[Column]:
    """Pystypeittopohjainen pilaridetektio.

    DBSCAN-klusterointi HYLÄTTY: työmaalla holvituet/tavara ketjuttavat
    pilarin naapurikramaan (eps-ketju) → jättiklusteri → footprint-hylky →
    0/92 GT-pilaria. Pilarin tuntomerkki ei ole irrallisuus vaan PYSTYPEITTO:
    XY-solu jonka z-binit ovat täynnä lattiasta kattoon. Ohut holvituki
    täyttää pystysuunnan mutta on ≤120mm → komponentin minimimitta hylkää."""
    from scipy.ndimage import label as _cc_label

    pts = np.asarray(cloud.points)
    if len(pts) < _MIN_CLUSTER_PTS:
        return []
    room_h = ceiling_z - floor_z
    if room_h < 1500.0:
        return []

    zmask = (pts[:, 2] > floor_z + _Z_MARGIN) & (pts[:, 2] < ceiling_z - _Z_MARGIN)
    band = pts[zmask]
    if len(band) < _MIN_CLUSTER_PTS:
        return []
    far = _dist_to_walls(band[:, :2], walls) > _WALL_MARGIN
    free = band[far]
    if len(free) < _MIN_CLUSTER_PTS:
        return []

    x0 = float(free[:, 0].min()); y0 = float(free[:, 1].min())
    ix = ((free[:, 0] - x0) / _CELL_MM).astype(np.int64)
    iy = ((free[:, 1] - y0) / _CELL_MM).astype(np.int64)
    z_lo = floor_z + _Z_MARGIN
    iz = ((free[:, 2] - z_lo) / _ZBIN_MM).astype(np.int64)
    nx, ny = int(ix.max()) + 1, int(iy.max()) + 1
    nz = max(int((ceiling_z - _Z_MARGIN - z_lo) / _ZBIN_MM), 1)
    iz = np.clip(iz, 0, nz - 1)

    # per-solu pystytäyttö: montako eri z-biniä on ≥2 pistettä
    flat = (ix * ny + iy) * nz + iz
    counts = np.bincount(flat, minlength=nx * ny * nz).reshape(nx, ny, nz)
    vfill = (counts >= 2).sum(axis=2) / nz
    cand = vfill >= _VFILL_MIN

    labels, ncomp = _cc_label(cand, structure=np.ones((3, 3), dtype=int))
    columns: list[Column] = []
    for k in range(1, ncomp + 1):
        cells_x, cells_y = np.nonzero(labels == k)
        ext_x = (cells_x.max() - cells_x.min() + 1) * _CELL_MM
        ext_y = (cells_y.max() - cells_y.min() + 1) * _CELL_MM
        if not (_COMP_MIN_MM <= max(ext_x, ext_y) <= _COMP_MAX_MM):
            continue
        # Rengastesti: aito pilari on IRRALLAAN — detektoimatta jääneen seinän
        # pala on pystytäytöltään pilarin näköinen, mutta sen LINJASSA on lisää
        # täyttösoluja. Jos renkaassa (2..6 solua bboxista) on muiden
        # komponenttien kandidaattisoluja, kyse on seinästä/hyllystä.
        rx0 = max(cells_x.min() - _RING_OUT, 0); rx1 = min(cells_x.max() + _RING_OUT + 1, nx)
        ry0 = max(cells_y.min() - _RING_OUT, 0); ry1 = min(cells_y.max() + _RING_OUT + 1, ny)
        ring = cand[rx0:rx1, ry0:ry1].copy()
        ix0 = max(cells_x.min() - _RING_IN, 0); ix1 = min(cells_x.max() + _RING_IN + 1, nx)
        iy0 = max(cells_y.min() - _RING_IN, 0); iy1 = min(cells_y.max() + _RING_IN + 1, ny)
        ring[ix0 - rx0:ix1 - rx0, iy0 - ry0:iy1 - ry0] = False
        if int(ring.sum()) >= _RING_MAX_CELLS:
            continue
        # pisteet komponentin soluista (+1 solun marginaali profiilia varten)
        in_comp = (
            (ix >= cells_x.min() - 1) & (ix <= cells_x.max() + 1)
            & (iy >= cells_y.min() - 1) & (iy <= cells_y.max() + 1)
        )
        cl = free[in_comp]
        if len(cl) < _MIN_CLUSTER_PTS:
            continue
        z_extent = float(cl[:, 2].max() - cl[:, 2].min())
        if z_extent < min(_MIN_HEIGHT_FRAC * room_h, _MIN_ABS_HEIGHT):
            continue
        xy = cl[:, :2]
        wx = float(np.percentile(xy[:, 0], 98) - np.percentile(xy[:, 0], 2))
        wy = float(np.percentile(xy[:, 1], 98) - np.percentile(xy[:, 1], 2))
        if not (_MIN_FOOTPRINT <= max(wx, wy) <= _MAX_FOOTPRINT):
            continue
        cx = float(xy[:, 0].mean()); cy = float(xy[:, 1].mean())
        shape, w, d = _profile(xy, cx, cy, wx, wy)
        columns.append(Column(
            id=f"column_{len(columns):03d}",
            confidence=round(min(1.0, len(cl) / 600.0), 3),
            classification="column",
            source=ElementSource(method="cluster", notes="vertical-fill"),
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

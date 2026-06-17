"""Seinägeometrian tarkentaminen ja suodatus. Sisään: Wall + cloud → ulos: Wall (päivitetty paksuus + filtteröity)."""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import Slab, Wall

_MAX_SEARCH_DIST = 400.0    # mm — kuinka kaukaa pisteitä haetaan normaalin suunnassa
_MIN_PEAK_PTS = 20          # min pisteitä huipussa jotta se on validi pinta
_BIN_MM = 6.0               # histogrammin resoluutio mm

_MIN_WALL_LENGTH = 600.0          # mm — lyhyemmät hylätään
_FLOOR_MARGIN = 400.0             # mm — seinä saa alkaa max tämän verran lattian yläpuolelta
_DEDUP_ANGLE_DEG = 15.0           # ° — alle tämän = sama suunta
_DEDUP_DIST_MM = 260.0            # mm — alle tämän = sama seinä (kohtisuora etäisyys)
_DEDUP_OVERLAP_FRAC = 0.40        # min pituuspeitto jotta katsotaan duplikaatiksi
_MAX_THICKNESS = 350.0            # mm — yli tämän = mittausvirhe → korvataan defaultilla
_DEFAULT_THICKNESS = 200.0        # mm


def filter_structural_walls(walls: list[Wall], slabs: list[Slab]) -> list[Wall]:
    """Hylkää kalusteista ja krääsästä syntyvät vääräpositiiviset seinät.

    Kaksi kriteeriä:
    1. Seinä alkaa läheltä lattiaa (z_min ≈ floor_z) — eliminoi kalusteplanot.
    2. Adaptiivinen confidence-kynnys — rakenteelliset seinät ovat suurimpia pintoja.
    """
    if not walls:
        return walls

    floor_z = _floor_z(slabs)

    # Lattia-läheisyyssuodatin (pääkriteeri)
    if floor_z is not None:
        walls = [w for w in walls if w.z_min <= floor_z + _FLOOR_MARGIN]

    # Confidence-kynnys (toissijainen)
    if walls:
        max_conf = max(w.confidence for w in walls)
        conf_threshold = max_conf * 0.30
        walls = [w for w in walls if w.confidence >= conf_threshold]

    # Minimipituus
    walls = [w for w in walls if _wall_length(w) >= _MIN_WALL_LENGTH]

    # Deduplointi — yhdistä lähes samat seinät
    return _deduplicate(walls)


def _deduplicate(walls: list[Wall]) -> list[Wall]:
    """Poistaa lähes päällekkäiset seinät — pitää korkeimman confidence-arvon."""
    kept: list[Wall] = []
    used = [False] * len(walls)
    walls_sorted = sorted(walls, key=lambda w: (-w.confidence, -_wall_length(w)))
    cos_thresh = float(np.cos(np.radians(_DEDUP_ANGLE_DEG)))

    for i, wa in enumerate(walls_sorted):
        if used[i]:
            continue
        kept.append(wa)
        da = _direction(wa)
        na = np.array([-da[1], da[0]])
        p0a = np.array(wa.axis[0], dtype=float)
        p1a = np.array(wa.axis[1], dtype=float)
        len_a = float(np.linalg.norm(p1a - p0a))

        for j, wb in enumerate(walls_sorted):
            if i == j or used[j]:
                continue
            db = _direction(wb)
            cos = abs(float(np.dot(da, db)))
            if cos < cos_thresh:
                continue

            # Kohtisuora etäisyys: pisteen p0b etäisyys wa:n suoralta
            p0b = np.array(wb.axis[0], dtype=float)
            p1b = np.array(wb.axis[1], dtype=float)
            perp_dist = abs(float(np.dot(p0b - p0a, na)))
            if perp_dist >= _DEDUP_DIST_MM:
                continue

            # Pituuspeitto wa:n suunnassa
            proj_a = np.array([float(p @ da) for p in [p0a, p1a]])
            proj_b = np.array([float(p @ da) for p in [p0b, p1b]])
            overlap = min(proj_a.max(), proj_b.max()) - max(proj_a.min(), proj_b.min())
            len_b = float(np.linalg.norm(p1b - p0b))
            if overlap < _DEDUP_OVERLAP_FRAC * min(len_a, len_b):
                continue

            used[j] = True

    return kept


def _direction(wall: Wall) -> np.ndarray:
    p0 = np.array(wall.axis[0])
    p1 = np.array(wall.axis[1])
    d = p1 - p0
    n = np.linalg.norm(d)
    return d / n if n > 0 else d


def _floor_z(slabs: list[Slab]) -> float | None:
    floors = [s.elevation for s in slabs if s.slab_type == "floor"]
    return min(floors) if floors else None


def _room_height(slabs: list[Slab]) -> float:
    floors = [s.elevation for s in slabs if s.slab_type == "floor"]
    ceilings = [s.elevation for s in slabs if s.slab_type == "ceiling"]
    if not floors or not ceilings:
        return 0.0
    return max(ceilings) - min(floors)


def _wall_length(wall: Wall) -> float:
    if len(wall.axis) < 2:
        return 0.0
    p0, p1 = wall.axis[0], wall.axis[1]
    return float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))


def refine_thicknesses(walls: list[Wall], cloud) -> list[Wall]:
    """Päivittää jokaisen seinän paksuuden pistepilvestä mitattuna."""
    pts = np.asarray(cloud.points)
    return [_refine(wall, pts) for wall in walls]


def _refine(wall: Wall, pts: np.ndarray) -> Wall:
    if len(wall.axis) < 2:
        return wall

    p0 = np.array(wall.axis[0])
    p1 = np.array(wall.axis[1])
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    if length < 1.0:
        return wall

    along = axis / length
    normal = np.array([-along[1], along[0]])

    mid = 0.5 * (p0 + p1)

    xy = pts[:, :2]
    proj_along = (xy - mid) @ along
    proj_normal = (xy - mid) @ normal

    margin = 200.0
    z_lo = wall.z_min + 150.0
    z_hi = wall.z_min + wall.height - 150.0
    mask = (np.abs(proj_along) <= length / 2.0 + margin) & \
           (np.abs(proj_normal) <= _MAX_SEARCH_DIST) & \
           (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    local_pts = proj_normal[mask]

    if len(local_pts) < _MIN_PEAK_PTS * 2:
        return wall

    thickness = _measure_thickness(local_pts, T_ref=wall.thickness)
    if thickness is not None:
        wall = wall.model_copy(update={"thickness": round(thickness, 1)})

    return wall


def _interp_peak(hist: np.ndarray, centers: np.ndarray, pk: int) -> float:
    if pk == 0 or pk >= len(hist) - 1:
        return float(centers[pk])
    y0, y1, y2 = float(hist[pk - 1]), float(hist[pk]), float(hist[pk + 1])
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-10:
        return float(centers[pk])
    delta = 0.5 * (y0 - y2) / denom
    bin_w = float(centers[1] - centers[0])
    return float(centers[pk]) + delta * bin_w


def _measure_thickness(proj: np.ndarray, T_ref: float = 200.0) -> float | None:
    """Histogrammi → kaksi huippua → niiden etäisyys = paksuus."""
    from scipy.signal import find_peaks

    p_min, p_max = float(proj.min()), float(proj.max())
    n_bins = max(int((p_max - p_min) / _BIN_MM), 10)
    counts, edges = np.histogram(proj, bins=n_bins)
    centers = 0.5 * (edges[:-1] + edges[1:])

    min_dist_bins = max(int(50.0 / _BIN_MM), 3)
    peaks, _ = find_peaks(counts, height=_MIN_PEAK_PTS, distance=min_dist_bins)

    if len(peaks) < 2:
        return None

    top2 = sorted(peaks, key=lambda i: counts[i], reverse=True)[:2]
    z0, z1 = centers[top2[0]], centers[top2[1]]
    thickness = abs(float(z1 - z0))

    if thickness < 50.0 or thickness > 500.0:
        return None

    return thickness

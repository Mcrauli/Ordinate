"""Seinägeometrian tarkentaminen ja suodatus. Sisään: Wall + cloud → ulos: Wall (päivitetty paksuus + filtteröity)."""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import Slab, Wall

_MAX_SEARCH_DIST = 230.0    # mm — kuinka kaukaa pisteitä haetaan normaalin suunnassa
                            # (kapea: ±400 nappasi viereisen huoneen seinän → 315/393mm)
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


def remove_dangling_walls(walls: list[Wall], free_tol: float = 400.0) -> list[Wall]:
    """Poistaa irralliset tynkäseinät: sisäseinä jonka jompikumpi pää on ilmassa
    (>free_tol kaikista muista seinistä) ei rajaa huonetta → roskaa. Perimetri
    (method=floorplan) säilytetään aina."""
    if len(walls) < 2:
        return walls
    kept: list[Wall] = []
    for i, w in enumerate(walls):
        if w.source.method == "floorplan":  # perimetriseinä → säilytä
            kept.append(w)
            continue
        if len(w.axis) < 2:
            kept.append(w)
            continue
        others = [o for j, o in enumerate(walls) if j != i and len(o.axis) >= 2]
        free_ends = 0
        for ep in (np.array(w.axis[0], float), np.array(w.axis[1], float)):
            dmin = min((_pt_seg_dist(ep, np.array(o.axis[0], float), np.array(o.axis[1], float))
                        for o in others), default=1e9)
            if dmin > free_tol:
                free_ends += 1
        # Vain aidosti kelluvat (MOLEMMAT päät irti) poistetaan — huonejakaja
        # yhdistyy vähintään toisesta päästä, joten se säilyy.
        if free_ends < 2:
            kept.append(w)
    return kept


def _pt_seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-9:
        return float(np.linalg.norm(p - a))
    t = max(0.0, min(1.0, float((p - a) @ ab) / L2))
    return float(np.linalg.norm(p - (a + t * ab)))


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
    if thickness is None:
        # Mittaus epäonnistui (yksipuolinen pinta / kohina) → käytä prioria.
        thickness = wall.thickness
    # Enforce sane range: yli max = mittausvirhe → default; alle min = nosta lattiaan.
    if thickness > _MAX_THICKNESS:
        thickness = _DEFAULT_THICKNESS
    elif thickness < 70.0:
        thickness = 70.0
    return wall.model_copy(update={"thickness": round(thickness, 1)})


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
    """Paksuus = seinän kahden pinnan etäisyys.

    Akseli on keskilinja → pinnat ovat offset 0:n eri puolilla (±T/2).
    Valitaan kummaltakin puolelta keskilinjaa LÄHIN merkittävä huippu — ei
    kahta korkeinta. Näin viereisen huoneen seinä (kauempana samalla puolella)
    ei sotke mittausta, eikä kohina toisella puolella tuota valepaksuutta.
    """
    from scipy.signal import find_peaks

    p_min, p_max = float(proj.min()), float(proj.max())
    n_bins = max(int((p_max - p_min) / _BIN_MM), 10)
    counts, edges = np.histogram(proj, bins=n_bins)
    centers = 0.5 * (edges[:-1] + edges[1:])

    min_dist_bins = max(int(50.0 / _BIN_MM), 3)
    peaks, _ = find_peaks(counts, height=_MIN_PEAK_PTS, distance=min_dist_bins)
    if len(peaks) == 0:
        return None

    peak_centers = centers[peaks]
    neg = peaks[peak_centers < 0.0]
    pos = peaks[peak_centers > 0.0]
    if len(neg) == 0 or len(pos) == 0:
        return None  # yksipuolinen pinta → priori hoitaa

    neg_face = neg[int(np.argmin(np.abs(centers[neg])))]
    pos_face = pos[int(np.argmin(np.abs(centers[pos])))]
    thickness = _interp_peak(counts, centers, pos_face) - _interp_peak(counts, centers, neg_face)

    if thickness < 60.0 or thickness > _MAX_THICKNESS:
        return None

    return float(thickness)

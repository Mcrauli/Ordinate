"""
Pohjapiirrosdetektori. Sisään: o3d.PointCloud → ulos: StructuralModel (seinät).

Algoritmi:
  1. Leikataan pilvi mid-korkeudelta (0.6–1.4 m lattian yllä) → kalusteet/katto pois
  2. 2D tiheysruudukko → binäärikuva
  3. HoughLinesP → raakaviivat
  4. Kulmahistogrammi → kaksi dominanttia suuntaa (rakennuksen pääakselit)
  5. Ryhmitellään viivat suunnan mukaan
  6. Yhdistetään rinnakkaiset viivat (sama seinätaso)
  7. Muunnetaan 3D Wall-objekteiksi
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from scipy.signal import find_peaks

from scan2bim.schemas.model import ElementSource, Metadata, StructuralModel, Wall
from scan2bim.core.segmentation.base import DetectorRegistry, ElementDetector

_GRID_MM = 25.0            # mm/pikseli
_MID_LO = 600.0            # mm lattian yläpuolelta
_MID_HI = 1400.0           # mm lattian yläpuolelta
_DENSITY_THRESH = 2        # min pisteitä per solu
_MORPH_K = 5               # morfologinen ydin
_MIN_LINE_MM = 1500.0      # lyhyemmät hylätään
_MAX_GAP_MM = 600.0        # max aukko viivassa
_LANE_MERGE_MM = 300.0     # alle tämän = sama seinätaso (kattaa molemmat seinäpinnat)
_ANGLE_TOL_DEG = 15.0      # toleranssi suuntaryhmitykseen
_ANGLE_BIN_DEG = 2.0       # kulmahistogrammin askelkoko
_CORNER_EXTEND_MM = 800.0  # kuinka kauas seinää jatketaan risteysten etsintään


@DetectorRegistry.register("floorplan")
class FloorPlanDetector(ElementDetector):
    """2D-pohjapiirrosdetektori joka korvaa RANSAC-tasosegmentoinnin."""

    def detect(self, cloud) -> StructuralModel:
        pts = np.asarray(cloud.points)
        if len(pts) < 200:
            return StructuralModel()

        floor_z, ceiling_z = _find_z_levels(pts)
        mid_xy = _mid_slice(pts, floor_z)
        if len(mid_xy) < 100:
            return StructuralModel()

        binary, x_min, y_min = _density_image(mid_xy)
        raw = _hough(binary)
        if raw is None or len(raw) == 0:
            return StructuralModel()

        dir1, dir2 = _dominant_directions(raw)
        group1 = _filter_by_dir(raw, dir1)
        group2 = _filter_by_dir(raw, dir2)

        merged1 = _merge_group(group1, dir1)
        merged2 = _merge_group(group2, dir2)

        # Leikkaa seinät risteyksissä → siistit nurkat
        merged1 = _trim_at_crossings(merged1, merged2)
        merged2 = _trim_at_crossings(merged2, merged1)

        height = ceiling_z - floor_z
        walls = _to_walls(merged1 + merged2, x_min, y_min, floor_z, height)

        model = StructuralModel(walls=walls)
        model.metadata = Metadata(detector_method="floorplan")
        return model


# ---------------------------------------------------------------------------
# Yksityiset apufunktiot
# ---------------------------------------------------------------------------

def _find_z_levels(pts: np.ndarray) -> tuple[float, float]:
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    n_bins = max(int((z_max - z_min) / 50), 10)
    counts, edges = np.histogram(z, bins=n_bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks, _ = find_peaks(counts, height=counts.max() * 0.10, distance=3)
    if len(peaks) >= 2:
        pz = centers[peaks]
        return float(pz.min()), float(pz.max())
    return z_min, z_max


def _mid_slice(pts: np.ndarray, floor_z: float) -> np.ndarray:
    lo, hi = floor_z + _MID_LO, floor_z + _MID_HI
    mask = (pts[:, 2] >= lo) & (pts[:, 2] <= hi)
    return pts[mask, :2]


def _density_image(xy: np.ndarray) -> tuple[np.ndarray, float, float]:
    x_min, y_min = float(xy[:, 0].min()), float(xy[:, 1].min())
    cols = max(int((xy[:, 0].max() - x_min) / _GRID_MM) + 2, 2)
    rows = max(int((xy[:, 1].max() - y_min) / _GRID_MM) + 2, 2)
    grid, _, _ = np.histogram2d(
        xy[:, 0], xy[:, 1], bins=[cols, rows],
        range=[[x_min, x_min + cols * _GRID_MM],
               [y_min, y_min + rows * _GRID_MM]],
    )
    binary = (grid.T >= _DENSITY_THRESH).astype(np.uint8) * 255
    k = np.ones((_MORPH_K, _MORPH_K), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
    return binary, x_min, y_min


def _hough(binary: np.ndarray):
    min_px = max(int(_MIN_LINE_MM / _GRID_MM), 5)
    gap_px = max(int(_MAX_GAP_MM / _GRID_MM), 3)
    return cv2.HoughLinesP(
        binary, rho=1, theta=np.pi / 180, threshold=min_px,
        minLineLength=min_px, maxLineGap=gap_px,
    )


def _dominant_directions(lines) -> tuple[float, float]:
    angles, weights = [], []
    for line in lines:
        x0, y0, x1, y1 = line[0]
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180
        angles.append(angle)
        weights.append(math.hypot(x1 - x0, y1 - y0))

    n_bins = int(180 / _ANGLE_BIN_DEG)
    hist, edges = np.histogram(angles, bins=n_bins, range=(0, 180), weights=weights)
    centers = 0.5 * (edges[:-1] + edges[1:])

    peaks, _ = find_peaks(hist, height=hist.max() * 0.08)
    if len(peaks) == 0:
        return 0.0, 90.0

    primary_idx = peaks[int(np.argmax(hist[peaks]))]
    dir1 = float(centers[primary_idx])

    dir2 = (dir1 + 90.0) % 180
    for p in sorted(peaks, key=lambda i: -hist[i]):
        angle = float(centers[p])
        diff = min(abs(angle - dir1), 180 - abs(angle - dir1))
        if diff > _ANGLE_TOL_DEG:
            dir2 = angle
            break

    return dir1, dir2


def _filter_by_dir(lines, target_deg: float) -> list:
    result = []
    for line in lines:
        x0, y0, x1, y1 = line[0]
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180
        diff = min(abs(angle - target_deg), 180 - abs(angle - target_deg))
        if diff <= _ANGLE_TOL_DEG:
            result.append(line)
    return result


def _merge_group(lines: list, direction_deg: float) -> list[tuple]:
    if not lines:
        return []

    rad = math.radians(direction_deg)
    d_vec = np.array([math.cos(rad), math.sin(rad)])
    n_vec = np.array([-math.sin(rad), math.cos(rad)])

    merge_px = _LANE_MERGE_MM / _GRID_MM

    # Laske jokaisen viivan kohtisuora asema
    lane_pos = []
    for line in lines:
        x0, y0, x1, y1 = line[0]
        mid = np.array([(x0 + x1) / 2.0, (y0 + y1) / 2.0])
        lane_pos.append(float(np.dot(mid, n_vec)))

    order = sorted(range(len(lines)), key=lambda i: lane_pos[i])
    used = [False] * len(lines)
    merged = []

    for i in order:
        if used[i]:
            continue
        group = [lines[i][0]]
        used[i] = True
        ref = lane_pos[i]

        for j in order:
            if used[j] or i == j:
                continue
            if abs(lane_pos[j] - ref) <= merge_px:
                group.append(lines[j][0])
                used[j] = True

        # Yhdistä ryhmä: laske pikselikoordinaateissa min/max suunnan mukaan
        all_pts = np.array(
            [[s[0], s[1]] for s in group] + [[s[2], s[3]] for s in group],
            dtype=float,
        )
        proj_along = np.dot(all_pts, d_vec)
        proj_perp = np.dot(all_pts, n_vec)

        avg_perp = float(np.mean(proj_perp))
        p0 = float(proj_along.min()) * d_vec + avg_perp * n_vec
        p1 = float(proj_along.max()) * d_vec + avg_perp * n_vec
        merged.append((p0, p1))

    return merged


def _trim_at_crossings(
    walls_a: list[tuple], walls_b: list[tuple]
) -> list[tuple]:
    """Leikkaa walls_a seinät siististi walls_b seinien risteyspisteissä."""
    extend_px = _CORNER_EXTEND_MM / _GRID_MM
    result = []

    for p0a, p1a in walls_a:
        d = p1a - p0a
        length = float(np.linalg.norm(d))
        if length < 1:
            result.append((p0a, p1a))
            continue
        d_n = d / length

        t_values = [0.0, 1.0]
        for p0b, p1b in walls_b:
            db = p1b - p0b
            lb = float(np.linalg.norm(db))
            if lb < 1:
                continue
            db_n = db / lb

            pt = _intersect_2d(p0a, d_n, p0b, db_n)
            if pt is None:
                continue

            # Parametrinen sijainti seinällä A ja B
            t_a = float(np.dot(pt - p0a, d_n)) / length
            t_b = float(np.dot(pt - p0b, db_n)) / lb

            # Hyväksytään jos leikkauspiste on lähellä molempia seiniä
            if (-extend_px / length <= t_a <= 1 + extend_px / length and
                    -extend_px / lb <= t_b <= 1 + extend_px / lb):
                t_values.append(t_a)

        if len(t_values) > 2:
            t_min = max(min(t_values), 0.0)
            t_max = min(max(t_values), 1.0)
            result.append((p0a + t_min * d, p0a + t_max * d))
        else:
            result.append((p0a, p1a))

    return result


def _intersect_2d(
    p1: np.ndarray, d1: np.ndarray,
    p2: np.ndarray, d2: np.ndarray,
) -> np.ndarray | None:
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
    det = float(np.linalg.det(A))
    if abs(det) < 1e-6:
        return None
    b = p2 - p1
    t = float(np.linalg.solve(A, b)[0])
    return p1 + t * d1


def _to_walls(
    merged: list[tuple],
    x_min: float, y_min: float,
    floor_z: float, height: float,
) -> list[Wall]:
    walls = []
    for idx, (p0_px, p1_px) in enumerate(merged):
        x0 = x_min + p0_px[0] * _GRID_MM
        y0 = y_min + p0_px[1] * _GRID_MM
        x1 = x_min + p1_px[0] * _GRID_MM
        y1 = y_min + p1_px[1] * _GRID_MM
        length = math.hypot(x1 - x0, y1 - y0)
        if length < _MIN_LINE_MM:
            continue
        walls.append(Wall(
            id=f"wall_{idx:03d}",
            confidence=round(min(1.0, length / 8000.0), 3),
            classification="wall",
            source=ElementSource(method="density"),
            axis=[[round(x0, 1), round(y0, 1)], [round(x1, 1), round(y1, 1)]],
            height=round(height, 1),
            thickness=200.0,
            z_min=round(floor_z, 1),
        ))
    return walls

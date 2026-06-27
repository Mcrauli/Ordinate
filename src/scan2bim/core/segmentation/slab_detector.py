"""Laattadetektio z-histogrammilla + OpenCV-kontuuri. Sisään: o3d.PointCloud → ulos: list[Slab]."""
from __future__ import annotations

import cv2
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from scan2bim.schemas.model import ElementSource, Slab

_MIN_SLAB_AREA  = 1_000_000.0   # mm²
_MIN_PLANE_PTS  = 100
_THICKNESS_DEFAULT = 200.0       # mm — betonirakenteen oletuspaksuus
_GRID_MM        = 25.0           # mm/pikseli kontuuriverkkoon (oli 80)
_DILATE_PX      = 3              # morfologinen laajennus pikseleinä
_CLOSE_PX       = 5              # closing-ydinkoko aukkojen sulkemiseen
_CONTOUR_SIMPLIFY = 0.008        # approxPolyDP epsilon-kerroin (pienempi = tarkempi)
_Z_BAND_MM      = 8.0            # ±mm lasertason ympärillä
_Z_BIN_MM       = 5.0            # histogrammin resoluutio
_Z_SMOOTH_BINS  = 4              # histogrammin tasoitusikkuna
_Z_MIN_FRAC     = 0.08           # minimikorkeus päähuipusta
_SLAB_PAIR_MM   = 450.0          # välipohjan kaksi pintaa (tai naapurikerroksen laatta) tämän sisällä


def detect_slabs(cloud) -> list[Slab]:
    """Tunnistaa lattia- ja kattopinnat pilvestä."""
    pts = np.asarray(cloud.points)
    if len(pts) < _MIN_PLANE_PTS:
        return []

    z_levels = _find_z_levels(pts)
    slabs: list[Slab] = []

    for idx, (z, slab_type) in enumerate(z_levels):
        precise_z = _refine_z(pts, z)
        thickness = _measure_thickness(pts, precise_z, slab_type)
        boundary = _contour_boundary(pts, precise_z)
        if boundary is None:
            continue
        area = _polygon_area(boundary)
        if area < _MIN_SLAB_AREA:
            continue
        slabs.append(Slab(
            id=f"slab_{idx:03d}",
            confidence=round(min(1.0, area / 20_000_000.0), 3),
            classification="slab",
            source=ElementSource(method="z_histogram"),
            slab_type=slab_type,
            boundary=[[round(x, 1), round(y, 1)] for x, y in boundary],
            elevation=round(float(precise_z), 1),
            thickness=round(float(thickness), 1),
        ))

    return slabs


def _find_z_levels(pts: np.ndarray) -> list[tuple[float, str]]:
    z = pts[:, 2]
    z_min, z_max = float(z.min()), float(z.max())
    n_bins = max(int((z_max - z_min) / _Z_BIN_MM), 20)
    counts, edges = np.histogram(z, bins=n_bins, range=[z_min, z_max])
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = uniform_filter1d(counts.astype(float), size=_Z_SMOOTH_BINS)

    peaks, _ = find_peaks(smooth, height=smooth.max() * _Z_MIN_FRAC, distance=5)
    if len(peaks) < 2:
        return [(z_min, "floor"), (z_max, "ceiling")]

    peak_z = np.sort(centers[peaks])

    # Lattia = alimman laattaparin YLÄpinta (kävelytaso); jos siivussa on naapurikerroksen
    # välipohja, alimmat kaksi huippua ovat lähekkäin → otetaan ylempi.
    floor = float(peak_z[0])
    for p in peak_z[1:]:
        if p - floor <= _SLAB_PAIR_MM:
            floor = float(p)
        else:
            break

    # Katto = ylimmän laattaparin ALApinta (huoneesta näkyvä pinta)
    ceiling = float(peak_z[-1])
    for p in peak_z[-2::-1]:
        if ceiling - p <= _SLAB_PAIR_MM:
            ceiling = float(p)
        else:
            break

    if ceiling - floor < 500.0:  # degeneroitu → palaa ääripäihin
        return [(float(peak_z[0]), "floor"), (float(peak_z[-1]), "ceiling")]
    return [(floor, "floor"), (ceiling, "ceiling")]


def _refine_z(pts: np.ndarray, z_approx: float) -> float:
    """Tarkka Z sub-bin-piikkisovituksella (paraabeli huipun kolmesta binistä).

    Laatta on terävä taso → tiheyshuippu osuu pinnalle. Piikkisovitus kestää
    lattian lähellä olevan krääsän (kalusteet, listat) joka vinouttaisi mediaanin.
    """
    near = pts[np.abs(pts[:, 2] - z_approx) < _Z_BAND_MM, 2]
    if len(near) < 10:
        return z_approx
    bin_mm = 1.0
    lo = float(near.min())
    nb = max(int((near.max() - lo) / bin_mm) + 1, 3)
    counts, edges = np.histogram(near, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    k = int(np.argmax(counts))
    if 0 < k < len(counts) - 1:
        c0, c1, c2 = float(counts[k - 1]), float(counts[k]), float(counts[k + 1])
        denom = c0 - 2.0 * c1 + c2
        delta = 0.5 * (c0 - c2) / denom if abs(denom) > 1e-9 else 0.0
        delta = max(-0.5, min(0.5, delta))
        return float(centers[k] + delta * bin_mm)
    return float(centers[k])


def _measure_thickness(pts: np.ndarray, z: float, slab_type: str) -> float:
    """Etsii toista pintaa laatan paksuuden mittaamiseksi."""
    # Katon yläpinta ei näy sisäskannauksessa → palautetaan aina oletus
    if slab_type != "floor":
        return _THICKNESS_DEFAULT
    # Lattia: katsotaan alle
    search = pts[pts[:, 2] < z - 20.0, 2]

    if len(search) < 50:
        return _THICKNESS_DEFAULT

    # Z-histogrammi → ensimmäinen merkittävä huippu = toinen pinta
    z_ref = z - 500.0 if slab_type == "floor" else z + 500.0
    candidate = search[np.abs(search - z_ref) < 480.0]
    if len(candidate) < 30:
        return _THICKNESS_DEFAULT

    counts, edges = np.histogram(candidate, bins=max(int(480 / _Z_BIN_MM), 4))
    smooth = uniform_filter1d(counts.astype(float), size=2)
    peaks, _ = find_peaks(smooth, height=smooth.max() * 0.2)
    if len(peaks) == 0:
        return _THICKNESS_DEFAULT

    centers = 0.5 * (edges[:-1] + edges[1:])
    best_z = float(centers[peaks[np.argmax(smooth[peaks])]])
    thickness = abs(z - best_z)
    return thickness if 180.0 < thickness < 600.0 else _THICKNESS_DEFAULT


def _contour_boundary(
    pts: np.ndarray, z: float
) -> list[tuple[float, float]] | None:
    """Pisteet z-tasolla → OpenCV-kontuuri → monikulmio."""
    mask = np.abs(pts[:, 2] - z) < _Z_BAND_MM
    slab_pts = pts[mask, :2]
    if len(slab_pts) < 10:
        return None

    x_min = float(slab_pts[:, 0].min())
    y_min = float(slab_pts[:, 1].min())
    cols = max(int((slab_pts[:, 0].max() - x_min) / _GRID_MM) + 2, 4)
    rows = max(int((slab_pts[:, 1].max() - y_min) / _GRID_MM) + 2, 4)

    grid, _, _ = np.histogram2d(
        slab_pts[:, 0], slab_pts[:, 1],
        bins=[cols, rows],
        range=[[x_min, x_min + cols * _GRID_MM],
               [y_min, y_min + rows * _GRID_MM]],
    )
    binary = (grid.T >= 1).astype(np.uint8) * 255

    close_k = np.ones((_CLOSE_PX, _CLOSE_PX), np.uint8)
    dilate_k = np.ones((_DILATE_PX, _DILATE_PX), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_k)
    binary = cv2.dilate(binary, dilate_k)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    epsilon = _CONTOUR_SIMPLIFY * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)

    result = []
    for pt in approx:
        px, py = pt[0]
        result.append((x_min + px * _GRID_MM, y_min + py * _GRID_MM))

    return result if len(result) >= 3 else None


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return abs(sum(
        xs[i] * ys[(i + 1) % n] - xs[(i + 1) % n] * ys[i]
        for i in range(n)
    )) / 2.0

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
_SIMPLIFY_MM    = 150.0          # approxPolyDP epsilon ABSOLUUTTISENA — suhteellinen
                                 # (0.008×arcLength) räjähtää lahdekkaalla kontuurilla:
                                 # varjolahdet paisuttavat arcLengthin → epsilon ~800 mm →
                                 # lahdet romahtavat ITSENSÄ LEIKKAAVAKSI siksakiksi
_Z_BAND_MM      = 8.0            # ±mm lasertason ympärillä
_FOOT_BAND_MM   = 40.0           # ±mm huonealan maskin z-kaista (8 mm on liian ohut → reikäinen)
_FOOT_CLOSE_PX  = 16             # 400 mm — sulkee kalusteiden keilausvarjot huonealasta
_FOOT_DILATE_PX = 2              # mitattu: reuna osuu aitoon sisäpintaan (3 px = +25 mm bias)
_FOOT_MIN_FLOOR_FRAC = 0.20      # huonealueen pinta-alasta oltava LATTIApisteiden peitossa:
                                 # katto vain sulkee varjot, se EI saa luoda aluetta. Mitattu
                                 # apt2: keilausvuoto lasin/oviaukon läpi 0.02, aidot huoneet
                                 # 0.60–0.97 (bedroom 0.74) → raja on kaukana molemmista
_Z_BIN_MM       = 5.0            # histogrammin resoluutio
_Z_SMOOTH_BINS  = 4              # histogrammin tasoitusikkuna
_Z_MIN_FRAC     = 0.08           # minimikorkeus päähuipusta
_SLAB_PAIR_MM   = 450.0          # välipohjan kaksi pintaa (tai naapurikerroksen laatta) tämän sisällä
_PAIR_MIN_RATIO = 0.7            # parikävely vain vertailukelpoiseen piikkiin: laattaparin pinnat
                                 # ovat ~yhtä vahvoja; alakatto/kotelo/kaapiston yläpinta on selvästi
                                 # heikompi eikä siihen saa astua (söisi huonekorkeutta)


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
    # Pehmustus: lattia/katto ovat pilven ääritasot → niiden piikit osuvat ensimmäiseen/
    # viimeiseen biniin, eikä find_peaks tunnista reunabiniä piikiksi. Laajenna aluetta
    # tasoitusikkunan verran molemmista päistä, jolloin reunapiikeillä on nollanaapurit.
    pad = _Z_SMOOTH_BINS * _Z_BIN_MM
    counts, edges = np.histogram(
        z, bins=n_bins + 2 * _Z_SMOOTH_BINS, range=[z_min - pad, z_max + pad]
    )
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = uniform_filter1d(counts.astype(float), size=_Z_SMOOTH_BINS)

    peaks, _ = find_peaks(smooth, height=smooth.max() * _Z_MIN_FRAC, distance=5)
    if len(peaks) < 2:
        return [(z_min, "floor"), (z_max, "ceiling")]

    order = np.argsort(centers[peaks])
    peak_z = centers[peaks][order]
    peak_h = smooth[peaks][order]

    # Lattia = alimman laattaparin YLÄpinta (kävelytaso); jos siivussa on naapurikerroksen
    # välipohja, alimmat kaksi huippua ovat lähekkäin → otetaan ylempi. Astutaan vain
    # VERTAILUKELPOISEEN piikkiin (laattaparin pinnat ~yhtä vahvoja) — selvästi heikompi
    # lähipiikki on kalustetaso/koroke, ei laattapari.
    floor = float(peak_z[0])
    floor_h = float(peak_h[0])
    for p, h in zip(peak_z[1:], peak_h[1:]):
        if p - floor <= _SLAB_PAIR_MM and h >= _PAIR_MIN_RATIO * floor_h:
            floor, floor_h = float(p), float(h)
        else:
            break

    # Katto = ylimmän laattaparin ALApinta (huoneesta näkyvä pinta). Sama vahvuusehto:
    # selvästi heikompi lähipiikki alapuolella on alakatto/kotelo/kaapiston yläpinta —
    # siihen astuminen söisi huonekorkeutta (tunnettu alakatto-ansa).
    ceiling = float(peak_z[-1])
    ceiling_h = float(peak_h[-1])
    for p, h in zip(peak_z[-2::-1], peak_h[-2::-1]):
        if ceiling - p <= _SLAB_PAIR_MM and h >= _PAIR_MIN_RATIO * ceiling_h:
            ceiling, ceiling_h = float(p), float(h)
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


def detect_floor_contours(
    cloud,
    elevation: float,
    min_area_m2: float = 1.5,
    ceiling_elevation: float | None = None,
    walls: list | None = None,
) -> list[list[tuple[float, float]]]:
    """Huonealan kontuurit (suurin ensin) — erilliset huoneet paksun seinän
    takana ovat omia polygonejaan eikä niitä saa pudottaa (perimetri ei muuten
    koskaan sulje niitä).

    Pelkkä ohut lattiaviipale EI riitä lähteeksi: kalusteiden keilausvarjot
    syövät siihen lahdet ulkoreunaan asti, ulkokontuuri kiertää joka lahden ja
    epsilon romahduttaa ne itsensä leikkaavaksi siksakiksi (mitattu asunnolla:
    25 kärkeä, 36.9 m² kun ala on 58 m², is_valid=False). Silloin signed area
    on merkityksetön → perimetrin ULOSPÄIN-normaali kääntyy väärin ja seiniä
    syntyy fiktiivisille diagonaalireunoille. Katossa ei ole kalusteita, joten
    lattia ∪ katto + varjojen sulkeminen antaa kiinteän ja validin alan.

    ``walls``: huoneala EI saa ylittää seinää. Ilman katkaisua yhtenäinen ala
    vuotaa oviaukoista ja lasiseinien läpi naapuritilaan (mitattu: 114 639
    kattopistettä yläseinän takana) → perimetri rakentaa seinän yhdistyneen
    alueen ULKOreunaan ja aito seinä kuolee snap-kaskadissa."""
    pts = np.asarray(cloud.points)
    zs = [elevation] if ceiling_elevation is None else [elevation, ceiling_elevation]
    grid = _occupancy_grid(pts, zs, _FOOT_BAND_MM, _FOOT_CLOSE_PX, _FOOT_DILATE_PX,
                           fill_holes=True)
    grid = _cut_walls(grid, walls)
    return _contours_from_grid(grid, min_area_m2 * 1e6,
                               floor_mask=_level_mask(pts, elevation, grid))


_CUT_MIN_MM = 120.0   # mm — katkaisuviivan minimileveys (ohut seinä ei katkaise 25 mm ruudukossa)


def _cut_walls(
    grid: tuple[np.ndarray, float, float] | None, walls: list | None
) -> tuple[np.ndarray, float, float] | None:
    """Nollaa seinien peittämät pikselit → huoneala katkeaa seinän kohdalta."""
    if grid is None or not walls:
        return grid
    binary, x_min, y_min = grid
    binary = binary.copy()
    for w in walls:
        axis = getattr(w, "axis", None)
        if not axis or len(axis) < 2:
            continue
        p0 = np.asarray(axis[0], dtype=float)
        p1 = np.asarray(axis[1], dtype=float)
        d = p1 - p0
        length = float(np.linalg.norm(d))
        if length < 1.0:
            continue
        u = d / length
        n = np.array([-u[1], u[0]])
        half = max(float(getattr(w, "thickness", 0.0)), _CUT_MIN_MM) / 2.0
        quad = np.array([p0 + n * half, p1 + n * half, p1 - n * half, p0 - n * half])
        px = np.column_stack([(quad[:, 0] - x_min) / _GRID_MM,
                              (quad[:, 1] - y_min) / _GRID_MM])
        cv2.fillPoly(binary, [np.round(px).astype(np.int32)], 0)
    return binary, x_min, y_min


def _contour_boundary(
    pts: np.ndarray, z: float
) -> list[tuple[float, float]] | None:
    """Pisteet z-tasolla → OpenCV-kontuuri → suurin monikulmio."""
    grid = _occupancy_grid(pts, [z], _Z_BAND_MM, _CLOSE_PX, _DILATE_PX, fill_holes=False)
    polys = _contours_from_grid(grid, min_area_mm2=0.0)
    return polys[0] if polys else None


def _occupancy_grid(
    pts: np.ndarray,
    z_levels: list[float],
    band: float,
    close_px: int,
    dilate_px: int,
    fill_holes: bool,
) -> tuple[np.ndarray, float, float] | None:
    """Binäärimaski (rivi=y, sarake=x) annettujen z-tasojen pisteistä."""
    sel = np.zeros(len(pts), dtype=bool)
    for z in z_levels:
        sel |= np.abs(pts[:, 2] - z) < band
    plane_pts = pts[sel, :2]
    if len(plane_pts) < 10:
        return None

    x_min = float(plane_pts[:, 0].min())
    y_min = float(plane_pts[:, 1].min())
    cols = max(int((plane_pts[:, 0].max() - x_min) / _GRID_MM) + 2, 4)
    rows = max(int((plane_pts[:, 1].max() - y_min) / _GRID_MM) + 2, 4)

    grid, _, _ = np.histogram2d(
        plane_pts[:, 0], plane_pts[:, 1],
        bins=[cols, rows],
        range=[[x_min, x_min + cols * _GRID_MM],
               [y_min, y_min + rows * _GRID_MM]],
    )
    binary = (grid.T >= 1).astype(np.uint8) * 255

    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                              np.ones((close_px, close_px), np.uint8))
    binary = cv2.dilate(binary, np.ones((dilate_px, dilate_px), np.uint8))
    if fill_holes:
        binary = _fill_holes(binary)
    return binary, x_min, y_min


def _fill_holes(binary: np.ndarray) -> np.ndarray:
    """Täytä sisäiset reiät (kalusteiden keilausvarjot) — flood-fill reunalta."""
    pad = cv2.copyMakeBorder(binary, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    ff_mask = np.zeros((pad.shape[0] + 2, pad.shape[1] + 2), np.uint8)
    cv2.floodFill(pad, ff_mask, (0, 0), 255)
    outside = pad[1:-1, 1:-1]
    return np.where(outside == 0, 255, binary).astype(np.uint8)


def _level_mask(
    pts: np.ndarray, z: float, grid: tuple[np.ndarray, float, float] | None
) -> np.ndarray | None:
    """Raaka (morfologioimaton) maski yhdeltä z-tasolta samaan ruudukkoon."""
    if grid is None:
        return None
    binary, x_min, y_min = grid
    rows, cols = binary.shape
    sel = np.abs(pts[:, 2] - z) < _FOOT_BAND_MM
    if not sel.any():
        return None
    hist, _, _ = np.histogram2d(
        pts[sel, 0], pts[sel, 1], bins=[cols, rows],
        range=[[x_min, x_min + cols * _GRID_MM], [y_min, y_min + rows * _GRID_MM]],
    )
    return hist.T >= 1


def _contours_from_grid(
    grid: tuple[np.ndarray, float, float] | None,
    min_area_mm2: float,
    floor_mask: np.ndarray | None = None,
) -> list[list[tuple[float, float]]]:
    if grid is None:
        return []
    binary, x_min, y_min = grid
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    px_area = _GRID_MM * _GRID_MM
    polys: list[tuple[float, list[tuple[float, float]]]] = []
    for c in sorted(contours, key=cv2.contourArea, reverse=True):
        area = float(cv2.contourArea(c)) * px_area
        if polys and area < min_area_mm2:
            break
        approx = cv2.approxPolyDP(c, _SIMPLIFY_MM / _GRID_MM, True)
        poly = [(x_min + float(pt[0][0]) * _GRID_MM, y_min + float(pt[0][1]) * _GRID_MM)
                for pt in approx]
        poly = _repair_polygon(poly)
        if poly is None:
            continue
        if floor_mask is not None and _floor_fraction(approx, binary.shape, floor_mask) \
                < _FOOT_MIN_FLOOR_FRAC:
            continue   # keilausvuoto (lasi/oviaukko): kattoa on, lattiaa ei → ei huone
        polys.append((area, poly))

    return [p for _, p in polys]


def _floor_fraction(approx: np.ndarray, shape, floor_mask: np.ndarray) -> float:
    region = np.zeros(shape, np.uint8)
    cv2.fillPoly(region, [approx.reshape(-1, 2).astype(np.int32)], 1)
    n = int(region.sum())
    if n == 0:
        return 0.0
    return float((region.astype(bool) & floor_mask).sum()) / n


def _repair_polygon(
    poly: list[tuple[float, float]]
) -> list[tuple[float, float]] | None:
    """Pudota tai korjaa itsensä leikkaava monikulmio.

    Fiktiivisiä perimetriseiniä ei saa rakentaa rikkinäiselle rajalle: signed
    area (= ulospäin-normaalin suunta) on silloin merkityksetön."""
    if len(poly) < 3:
        return None
    try:
        from shapely.geometry import Polygon
    except ImportError:
        return poly
    sp = Polygon(poly)
    if sp.is_valid:
        return poly
    fixed = sp.buffer(0)
    if fixed.is_empty:
        return None
    if fixed.geom_type == "MultiPolygon":
        fixed = max(fixed.geoms, key=lambda g: g.area)
    if fixed.geom_type != "Polygon" or fixed.area <= 0.0:
        return None
    return [(round(float(x), 1), round(float(y), 1))
            for x, y in fixed.exterior.coords[:-1]]


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

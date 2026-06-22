"""Oviaukkojen ja ikkunoiden detektio seinäpinnoilta.

Algoritmi:
  1. Projisoidaan pisteet seinätasolle (along-wall × Z)
  2. 1D kolonnidensiteetti: pisteet per along-sarake
  3. Löydetään "sparse" sarakkeet (< 15 % mediaanista) → aukkokandidaatit
  4. Ryhmitellään peräkkäiset sparse-sarakkeet
  5. Aukon korkeus estimoidaan NAAPURISARAKKEIDEN Z-profiilista
     (ei tyhjistä sarakkeista, joissa korkeus olisi aina koko seinä)
  6. Suodatetaan koon mukaan, luokitellaan ovi/ikkuna
"""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import ElementSource, Opening, Wall

_FACE_TOL = 20.0          # mm — toleranssi seinän pintaa vasten
_GRID_MM = 30.0           # mm/solu (pienempi → erottaa yksittäiset ikkunat)
_GAP_THRESHOLD = 0.20     # sarake on "sparse" jos pisteitä < 20 % mediaanista
_NEIGHBOR_COLS = 3        # kuinka monta naapurisaraketta katsotaan Z-profiilin laskentaan
_MIN_PTS_BASELINE = 30    # min pisteitä per kolonni jotta seinä on "datallinen"
_MIN_W = 500.0            # mm — kapein aukko (realistisin pienin ikkuna)
_MAX_W = 2500.0           # mm — levein aukko
_MAX_FRACTION = 0.50      # aukko ei voi olla yli 50 % seinänpituudesta
_MIN_H = 600.0            # mm — matalin aukko
_MAX_H_FRACTION = 0.90    # aukon korkeus max 90 % seinänkorkeudesta
_DOOR_SILL_MAX = 500.0    # mm — ovi jos sill_height < tämä (ikkunan sill tyyp. >=900)
_DOOR_MIN_W = 700.0       # mm — ovi min leveys (alle tämän = ikkuna tai hylätään)
_DOOR_MAX_W = 1500.0      # mm — ovi max leveys
_DOOR_MAX_H = 2400.0      # mm — ovi max korkeus
_NOISE_FILL_CELLS = 2     # täytettävät kohinaaukot (z-soluja)
_MIN_OPEN_CELLS = 40      # min soluja yhtenäisessä aukossa (kohinaklusterit pois)


def detect_openings(
    walls: list[Wall], cloud, floor_z: float,
    scanner_origins: list | None = None,
) -> list[Opening]:
    pts = np.asarray(cloud.points)
    origins = [np.asarray(o, dtype=float) for o in (scanner_origins or [])]
    openings: list[Opening] = []
    counter = 0
    for wall in walls:
        new = _wall_openings(wall, pts, floor_z, counter)
        if origins:
            new = [op for op in new if not _is_occlusion_shadow(op, wall, pts, origins, floor_z)]
        openings.extend(new)
        counter += len(new)
    return openings


def _is_occlusion_shadow(
    opening: Opening, wall: Wall, pts: np.ndarray,
    origins: list[np.ndarray], floor_z: float,
) -> bool:
    """True jos aukko on kalusteen okkluusiovarjo: skannerin ja seinän välissä on
    pistejoukko joka projisoituu juuri aukon alueelle. Oikea aukko → näkölinja vapaa."""
    if len(wall.axis) < 2:
        return False
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    d = p1 - p0
    length = float(np.linalg.norm(d))
    if length < 1.0:
        return False
    along = d / length
    normal = np.array([-along[1], along[0]])
    plane_D = float(np.dot(normal, p0))

    a0 = opening.position_along
    a1 = a0 + opening.width
    z0 = floor_z + opening.sill_height
    z1 = z0 + opening.opening_height
    patch_area = max(opening.width * opening.opening_height, 1.0)
    occ_thr = max(int(patch_area / (40.0 * 40.0) * 0.25), 80)  # ~25 % katepeitto

    pN = pts[:, :2] @ normal
    for S in origins:
        sN = float(S[:2] @ normal)
        wall_gap = plane_D - sN           # etäisyys skannerista seinätasolle (normaalin suunnassa)
        if abs(wall_gap) < 100.0:
            continue
        denom = pN - sN
        with np.errstate(divide="ignore", invalid="ignore"):
            f = wall_gap / denom          # skaala jolla säde S→P osuu seinätasolle
        # P on skannerin ja seinän VÄLISSÄ (f>1) ja selvästi seinän edessä
        front = np.isfinite(f) & (f > 1.05) & (np.abs(denom) < abs(wall_gap) - 50.0) & (np.sign(denom) == np.sign(wall_gap))
        if not front.any():
            continue
        Pf = pts[front]
        ff = f[front][:, None]
        hit = S[None, :] + ff * (Pf - S[None, :])      # osumapiste seinätasolla
        hit_along = (hit[:, :2] - p0) @ along
        inside = (hit_along >= a0) & (hit_along <= a1) & (hit[:, 2] >= z0) & (hit[:, 2] <= z1)
        if int(inside.sum()) >= occ_thr:
            return True
    return False


def _wall_openings(
    wall: Wall, pts: np.ndarray, floor_z: float, start_idx: int
) -> list[Opening]:
    if len(wall.axis) < 2:
        return []

    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    d = p1 - p0
    length = float(np.linalg.norm(d))
    if length < 1.0:
        return []

    along = d / length
    normal = np.array([-along[1], along[0]])
    plane_D = float(np.dot(normal, p0))

    signed_dist = pts[:, :2] @ normal - plane_D   # negatiivinen tai positiivinen
    dist_to_plane = np.abs(signed_dist)
    proj_along = (pts[:, :2] - p0) @ along
    z_lo = wall.z_min - 100.0
    z_hi = wall.z_min + wall.height + 100.0

    # Käytetään vain YHTÄ seinäpintaa (sisäpinta = se jolla on enemmän pisteitä).
    # Kahden pinnan käyttö täyttää aukot ulkopuolelta läpi näkyvillä pisteillä
    # (esim. ulkoseinässä ikkunan läpi näkyy ulkopinta) → ikkunat katoavat.
    half_t = wall.thickness / 2.0
    pos_face_count = int((np.abs(signed_dist - half_t) < _FACE_TOL).sum())
    neg_face_count = int((np.abs(signed_dist + half_t) < _FACE_TOL).sum())
    if pos_face_count >= neg_face_count:
        near_face = np.abs(signed_dist - half_t) < _FACE_TOL
    else:
        near_face = np.abs(signed_dist + half_t) < _FACE_TOL
    near_center = dist_to_plane < _FACE_TOL
    on_wall_plane = near_face | near_center

    mask = (
        on_wall_plane
        & (proj_along >= -100.0)
        & (proj_along <= length + 100.0)
        & (pts[:, 2] >= z_lo)
        & (pts[:, 2] <= z_hi)
    )
    if mask.sum() < 50:
        return []

    proj = proj_along[mask]
    zvals = pts[mask, 2]

    n_x = max(int(length / _GRID_MM) + 1, 2)
    n_z = max(int(wall.height / _GRID_MM) + 1, 2)

    grid, xe, ze = np.histogram2d(
        proj, zvals,
        bins=[n_x, n_z],
        range=[[0.0, length], [wall.z_min, wall.z_min + wall.height]],
    )
    # Tiheystasoitus: yksittäinen harva rasteri ei jätä valeaukkoja soluvälistä
    from scipy.ndimage import uniform_filter
    dens = uniform_filter(grid.astype(float), size=2)
    occ_cells = dens[dens > 0]
    if len(occ_cells) < 10:
        return []
    cell_base = float(np.median(occ_cells))
    occ = dens > 0.25 * cell_base  # bool (n_x, n_z)

    # 1D: pisteitä per x-sarake
    col_pts = grid.sum(axis=1)
    pos_cols = col_pts[col_pts > 0]
    if len(pos_cols) < 5:
        return []
    baseline = float(np.median(pos_cols))
    if baseline < _MIN_PTS_BASELINE:
        return []

    is_gap_col = col_pts < _GAP_THRESHOLD * baseline

    return _find_openings(
        is_gap_col, occ, col_pts, xe, ze, n_x, n_z,
        length, wall, floor_z, start_idx,
    )


def _find_openings(
    is_gap_col: np.ndarray,
    occ: np.ndarray,
    col_pts: np.ndarray,
    xe: np.ndarray,
    ze: np.ndarray,
    n_x: int,
    n_z: int,
    length: float,
    wall: Wall,
    floor_z: float,
    start_idx: int,
) -> list[Opening]:
    """2D-aukkohaku: aukko = yhtenäinen alue, jossa seinäpinta puuttuu mutta
    ympärillä (vasen/oikea/ylä/ala) on pintaa. Toimii osakorkuisille aukoille
    (ikkuna jättää sill+lintel, ovi jättää lintelin) — 1D-sarakemetodi ei.
    """
    from scipy.ndimage import label, binary_closing

    # Seinän tyypillinen Z-profiili tiheistä sarakkeista: mille riveille pintaa kuuluu
    global_z_occ = np.zeros(n_z, dtype=bool)
    for k in range(n_x):
        if not is_gap_col[k] and col_pts[k] > 0:
            global_z_occ |= occ[k]
    _fill_noise_in_zprofile(global_z_occ, _NOISE_FILL_CELLS)
    wall_rows = np.flatnonzero(global_z_occ)
    if len(wall_rows) < 2:
        return []
    z_lo_row, z_hi_row = int(wall_rows.min()), int(wall_rows.max())

    # Seinän X-laajuus: tiheiden sarakkeiden väli (rajaa aukot seinän sisälle)
    dense_idx = np.flatnonzero(~is_gap_col & (col_pts > 0))
    if len(dense_idx) < 2:
        return []
    x_lo, x_hi = int(dense_idx.min()), int(dense_idx.max())

    # "Puuttuva pinta": rivi kuuluu seinään mutta solu on tyhjä
    missing = (~occ) & global_z_occ[None, :]
    missing[:x_lo] = False
    missing[x_hi + 1:] = False
    missing[:, :z_lo_row] = False
    missing[:, z_hi_row + 1:] = False
    # Sulje pienet kohinaaukot, jotta yksi aukko ei pirstoudu
    missing = binary_closing(missing, structure=np.ones((2, 2)))

    labels, n = label(missing, structure=np.ones((3, 3)))
    openings: list[Opening] = []
    for lab in range(1, n + 1):
        xs, zs = np.where(labels == lab)
        xi0, xi1 = int(xs.min()), int(xs.max())
        zi0, zi1 = int(zs.min()), int(zs.max())

        width = float(xe[xi1 + 1] - xe[xi0])
        z_start = float(ze[zi0])
        z_end = float(ze[zi1 + 1])
        height = z_end - z_start

        if not _is_valid_opening(width, height, length, wall.height):
            continue
        # Soliditeetti: aukon on oltava täyteläinen suorakaide, ei hajanaista kohinaa
        bbox_cells = (xi1 - xi0 + 1) * (zi1 - zi0 + 1)
        if len(xs) < _MIN_OPEN_CELLS or len(xs) < 0.55 * bbox_cells:
            continue
        # Vaadi seinämateriaalia molemmin puolin samalla Z-kaistalla (ei seinän pää)
        band = slice(zi0, zi1 + 1)
        left_ok = xi0 > x_lo and occ[max(x_lo, xi0 - _NEIGHBOR_COLS):xi0, band].any()
        right_ok = xi1 < x_hi and occ[xi1 + 1:min(x_hi + 1, xi1 + 1 + _NEIGHBOR_COLS), band].any()
        if not (left_ok and right_ok):
            continue

        # Hylkää leveät+matalat haamut (esim. 2.3m × 0.7m harva katto-/lattiakaista)
        if width > 2.0 * height:
            continue
        sill_h = max(z_start - floor_z, 0.0)
        otype = _classify(sill_h, width, height)
        if otype == "unknown":
            continue   # vain varmat ovet/ikkunat → vähemmän virhehavaintoja
        openings.append(Opening(
            id=f"opening_{start_idx + len(openings):03d}",
            confidence=round(min(1.0, (width / 900.0) * (height / 2000.0)), 3),
            classification="opening",
            source=ElementSource(method="opening"),
            opening_type=otype,
            wall_id=wall.id,
            position_along=round(float(xe[xi0]), 1),
            width=round(width, 1),
            sill_height=round(sill_h, 1),
            opening_height=round(height, 1),
        ))

    return openings


def _fill_noise_in_zprofile(occ: np.ndarray, max_gap: int) -> None:
    """Täytä lyhyet aukot (≤ max_gap solua) boolean-profiilissa."""
    n = len(occ)
    in_gap = False
    gap_start = 0
    for z in range(n):
        if not occ[z]:
            if not in_gap:
                in_gap = True
                gap_start = z
        else:
            if in_gap:
                in_gap = False
                if z - gap_start <= max_gap:
                    occ[gap_start:z] = True


def _largest_true_span(mask: np.ndarray, ze: np.ndarray, n_z: int) -> tuple[float, float] | None:
    """Suurin True-jakso boolean-maskissa → (z_alku, z_loppu) tai None."""
    best: tuple[float, float] | None = None
    best_len = 0
    in_span = False
    span_start = 0
    for z in range(n_z):
        if mask[z]:
            if not in_span:
                in_span = True
                span_start = z
        else:
            if in_span:
                in_span = False
                if z - span_start > best_len:
                    best_len = z - span_start
                    best = (float(ze[span_start]), float(ze[z]))
    if in_span and n_z - span_start > best_len:
        best = (float(ze[span_start]), float(ze[n_z]))
    return best


def _infer_height_from_top(
    global_z_occ: np.ndarray, ze: np.ndarray, n_z: int, wall: Wall
) -> tuple[float, float] | None:
    """Kun gap-sarakkeet ovat täysin tyhjiä: etsitään seinän ylin täynnä-alue
    ja arvataan aukko siitä alas lattiaan asti."""
    # Etsi alin Z-rivi jossa seinäpisteitä (= seinän yläreunan alku)
    for z in range(n_z - 1, -1, -1):
        if global_z_occ[z]:
            top_z = float(ze[z + 1]) if z + 1 <= n_z else float(ze[n_z])
            # Aukko alkaa lattialta, päättyy tähän
            bottom_z = float(ze[0])
            height = top_z - bottom_z
            if height > _MIN_H:
                return (bottom_z, min(top_z, bottom_z + _DOOR_MAX_H))
    return None


def _is_valid_opening(width: float, height: float, wall_length: float, wall_height: float) -> bool:
    if not (_MIN_W <= width <= _MAX_W):
        return False
    if width > wall_length * _MAX_FRACTION:
        return False
    if not (_MIN_H <= height <= wall_height * _MAX_H_FRACTION):
        return False
    return True


def _classify(sill_h: float, width: float, height: float) -> str:
    if sill_h < _DOOR_SILL_MAX and width >= _DOOR_MIN_W and width <= _DOOR_MAX_W and height <= _DOOR_MAX_H:
        return "door"
    if sill_h >= _DOOR_SILL_MAX or width < _DOOR_MIN_W:
        return "window"
    return "unknown"

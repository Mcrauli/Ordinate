"""Oviaukkojen ja ikkunoiden detektio seinäpinnoilta.

Algoritmi (sarakepohjainen):
  1. Projisoidaan pisteet seinätasolle (along-wall × Z), rakennetaan 2D-miehitysruudukko.
  2. Sarake on "seinäinen" jos sen alakaista (~150–1400 mm) on TÄYNNÄ riittävän
     korkealta (osuus täysiä rivejä ≥ 0.45). Kalustepiste osuu vain ohueen
     viipaleeseen eikä tee sarakkeesta seinäistä → oviaukot eivät pirstoudu.
  3. Aukko = peräkkäisten EI-seinäisten sarakkeiden jakso seinän sisällä.
     Ohuet (≤2 solua) yksittäiset solidijaksot aukon sisällä silloitetaan.
  4. Sill ja korkeus aukon sisäsarakkeiden Z-profiilista (≥50 % sarakkeista
     täynnä → oikea sokkeli/lintel; yksittäinen kaluste ei).
  5. Reunaehto: seinämateriaalia molemmin puolin TAI seinän pää on ankkuroitu
     toiseen seinään (nurkka/T-liitos → uskottava oviaukko nurkan vieressä).
  6. Luokitellaan ovi/ikkuna sill-korkeuden mukaan.
"""
from __future__ import annotations

import os

import numpy as np

from scan2bim.schemas.model import ElementSource, Opening, Wall

_DEBUG = os.environ.get("OPENING_DEBUG") == "1"


def _dbg(wall, width, height, z_start, floor_z, reason: str) -> None:
    if _DEBUG:
        print(f"[op] {wall.id} L={_wlen(wall):.0f} cand w={width:.0f} h={height:.0f} "
              f"sill={max(z_start - floor_z, 0.0):.0f} -> {reason}")


def _wlen(wall) -> float:
    p0 = np.asarray(wall.axis[0], float)
    p1 = np.asarray(wall.axis[1], float)
    return float(np.linalg.norm(p1 - p0))

_FACE_TOL = 20.0          # mm — toleranssi seinän pintaa vasten
_GRID_MM = 30.0           # mm/solu (pienempi → erottaa yksittäiset ikkunat)
_NEIGHBOR_COLS = 3        # kuinka monta naapurisaraketta katsotaan reunaehtoon
_MIN_PTS_BASELINE = 30    # min pisteitä per kolonni jotta seinä on "datallinen"
_MIN_W = 500.0            # mm — kapein aukko (realistisin pienin ikkuna)
_MAX_W = 2500.0           # mm — levein aukko
_MAX_FRACTION = 0.50      # aukko ei voi olla yli 50 % seinänpituudesta
_MIN_H = 600.0            # mm — matalin aukko
_DOOR_SILL_MAX = 250.0    # mm — ovi alkaa lattiatasosta; korkeampi sokkeli = ikkuna
                          # (matalasokkeliset ranskalaiset ikkunat ~300-500 eivät ole ovia)
_DOOR_MAX_W = 1800.0      # mm — ovi max leveys (pari-/liukuovi ~1600-1800; leveämpi
                          # lattiatason aukko = lasiseinä/ikkuna)


def detect_openings(
    walls: list[Wall], cloud, floor_z: float,
    scanner_origins: list | None = None,
) -> list[Opening]:
    pts = np.asarray(cloud.points)
    origins = [np.asarray(o, dtype=float) for o in (scanner_origins or [])]
    openings: list[Opening] = []
    counter = 0
    for wall in walls:
        new = _wall_openings(wall, pts, floor_z, counter, walls)
        if origins:
            new = [op for op in new if not _is_occlusion_shadow(op, wall, pts, origins, floor_z)]
        openings.extend(new)
        counter += len(new)
    return openings


def _wall_end_anchors(wall: Wall, walls: list[Wall]) -> tuple[bool, bool]:
    """Onko seinän alku-/loppupäässä toinen seinä (nurkka/T-liitos)?
    Jos on, päässä oleva aukko on uskottava (oviaukko nurkan vieressä)."""
    if len(wall.axis) < 2:
        return False, False
    p0 = np.array(wall.axis[0], float)
    p1 = np.array(wall.axis[1], float)
    _REACH = 500.0  # mm — kuinka lähellä toisen seinän on oltava
    start_anchor = False
    end_anchor = False
    for other in walls:
        if other.id == wall.id or len(other.axis) < 2:
            continue
        for q in (np.array(other.axis[0], float), np.array(other.axis[1], float)):
            if np.linalg.norm(q - p0) < _REACH:
                start_anchor = True
            if np.linalg.norm(q - p1) < _REACH:
                end_anchor = True
    return start_anchor, end_anchor


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
    wall: Wall, pts: np.ndarray, floor_z: float, start_idx: int,
    all_walls: list[Wall],
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

    col_pts = grid.sum(axis=1)
    pos_cols = col_pts[col_pts > 0]
    if len(pos_cols) < 5:
        return []
    baseline = float(np.median(pos_cols))
    if baseline < _MIN_PTS_BASELINE:
        if _DEBUG:
            print(f"[op] {wall.id} L={length:.0f} REJECT baseline={baseline:.1f} < {_MIN_PTS_BASELINE}")
        return []

    start_anchor, end_anchor = _wall_end_anchors(wall, all_walls)
    if _DEBUG:
        print(f"[op] {wall.id} L={length:.0f} baseline={baseline:.0f} "
              f"maskpts={int(mask.sum())} anchors={start_anchor},{end_anchor}")

    found = _find_openings(
        occ, col_pts, xe, ze, n_x, n_z,
        length, wall, floor_z, start_idx, start_anchor, end_anchor,
    )
    # Reunatarkennus raakapisteistä: 30mm-gridi kvantisoi aukon reunat ±15mm +
    # siltaukset. Step-sovitus (tyhjä aukko vs täysi seinäpinta) vie reunat ja
    # sillin/ylityksen mm-tasolle.
    return [_refine_opening_edges(op, proj, zvals, floor_z, wall) for op in found]


_RE_WIN = 150.0    # mm — hakuikkuna gridireunasta molempiin suuntiin
_RE_BIN = 5.0      # mm — step-sovituksen resoluutio
_RE_MARGIN = 60.0  # mm — z/along-marginaali profiilipisteitä valittaessa


def _step_edge(vals: np.ndarray, e0: float, sign: float) -> float | None:
    """Reunan paikka: maksimoi tiheyskontrasti (tyhjä aukon puoli vs täysi seinä).

    sign=+1: seinä reunan oikealla (aukko vasemmalla); sign=-1: peilikuva."""
    sel = vals[(vals >= e0 - _RE_WIN) & (vals <= e0 + _RE_WIN)]
    if len(sel) < 30:
        return None
    edges = np.arange(e0 - _RE_WIN, e0 + _RE_WIN + _RE_BIN, _RE_BIN)
    hist, edges = np.histogram(sel, bins=edges)
    c = np.cumsum(hist)
    total = float(c[-1])
    n = len(hist)
    best, best_k = -1.0, None
    for k in range(2, n - 2):
        left = float(c[k]) / (k + 1)              # keskitiheys reunan vasemmalla
        right = (total - float(c[k])) / (n - k - 1)
        contrast = (right - left) * sign
        if contrast > best:
            best, best_k = contrast, k
    if best_k is None or best <= 0:
        return None
    return float(edges[best_k + 1])


def _refine_opening_edges(op: Opening, proj: np.ndarray, zvals: np.ndarray,
                          floor_z: float, wall: Wall) -> Opening:
    a0 = op.position_along
    a1 = a0 + op.width
    z0 = floor_z + op.sill_height
    z1 = z0 + op.opening_height

    # Reunat: pisteet aukon z-alueelta (marginaalilla) → along-step
    zm = (zvals >= z0 + _RE_MARGIN) & (zvals <= z1 - _RE_MARGIN)
    new_a0 = _step_edge(proj[zm], a0, -1.0) if zm.sum() >= 30 else None
    new_a1 = _step_edge(proj[zm], a1, +1.0) if zm.sum() >= 30 else None
    r0 = new_a0 if new_a0 is not None else a0
    r1 = new_a1 if new_a1 is not None else a1
    if r1 - r0 < _MIN_W * 0.8:
        r0, r1 = a0, a1

    # Silli ja ylitys: pisteet aukon along-alueelta → z-step
    am = (proj >= r0 + _RE_MARGIN) & (proj <= r1 - _RE_MARGIN)
    new_z0 = _step_edge(zvals[am], z0, -1.0) if am.sum() >= 30 else None
    new_z1 = _step_edge(zvals[am], z1, +1.0) if am.sum() >= 30 else None
    rz0 = new_z0 if new_z0 is not None and op.sill_height > 50.0 else z0
    rz1 = new_z1 if new_z1 is not None else z1
    if rz1 - rz0 < _MIN_H * 0.8:
        rz0, rz1 = z0, z1

    return op.model_copy(update={
        "position_along": round(r0, 1),
        "width": round(r1 - r0, 1),
        "sill_height": round(max(rz0 - floor_z, 0.0), 1),
        "opening_height": round(min(rz1 - rz0, wall.height), 1),
    })


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Palauta True-jaksot (alku, loppu_inclusive) boolean-vektorista."""
    out: list[tuple[int, int]] = []
    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def _find_openings(
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
    start_anchor: bool,
    end_anchor: bool,
) -> list[Opening]:
    """Sarakepohjainen aukkohaku.

    Aukko = pystysuora kaista sarakkeita joissa seinämassa puuttuu LATTIAKAISTALTA
    (oviaukot ja ikkunat näkyvät pistepilvessä lattiasta-ylös -rakoina; lintel jää
    usein skannaamatta → rako ulottuu kattoon). Sill/korkeus mitataan sarakkeen
    Z-profiilista. Reunaehto: seinämateriaalia molemmin puolin TAI seinän pää on
    ankkuroitu toiseen seinään (nurkka/T-liitos → oviaukko nurkassa).
    """
    z0 = float(ze[0])

    # Rivivälit Z-arvoina
    z_centers = 0.5 * (ze[:-1] + ze[1:])

    # Alakaista ~150–1400 mm lattiasta. Solidi seinä täyttää kaistan koko
    # korkeudelta; kaluste/clutter osuu vain ohueen viipaleeseen. Siksi vaadi
    # että RIITTÄVÄ OSUUS kaistan riveistä on täynnä — yksittäinen kalustepiste
    # ei tee sarakkeesta "seinäistä" (muuten oviaukot pirstoutuvat).
    floor_band_lo = z0 + 150.0
    floor_band_hi = z0 + 1400.0
    fb_rows = np.where((z_centers >= floor_band_lo) & (z_centers <= floor_band_hi))[0]
    if len(fb_rows) < 2:
        return []

    fb_frac = occ[:, fb_rows].mean(axis=1)   # osuus täysiä rivejä per sarake
    col_floor_solid = fb_frac >= 0.45
    # Sarakkeessa on lainkaan dataa (erottaa skannaamattoman seinän aukosta)
    col_has_data = col_pts > 0

    # Seinän todellinen X-laajuus = lattialla solidien sarakkeiden väli
    solid_idx = np.flatnonzero(col_floor_solid)
    if len(solid_idx) < 2:
        return []
    x_lo, x_hi = int(solid_idx.min()), int(solid_idx.max())

    # Aukkosarake = seinän sisällä, ei lattiasolidia
    gap_col = ~col_floor_solid
    gap_col[:x_lo] = False
    gap_col[x_hi + 1:] = False
    # Silloita ohuet yksittäiset solidisarakkeet (kaluste/karmin reuna aukon sisällä):
    # ≤2 solua leveä solidijakso aukon sisällä → osa samaa aukkoa.
    for (s, e) in _runs(col_floor_solid & (np.arange(n_x) > x_lo) & (np.arange(n_x) < x_hi)):
        if e - s + 1 <= 2:
            gap_col[s:e + 1] = True

    # Seinän tyypillinen yläreuna (lintel-taso) solideista sarakkeista
    solid_top_rows = []
    for k in solid_idx:
        rows = np.flatnonzero(occ[k])
        if len(rows):
            solid_top_rows.append(int(rows.max()))
    wall_top_row = int(np.median(solid_top_rows)) if solid_top_rows else n_z - 1
    wall_top_z = float(ze[min(wall_top_row + 1, n_z)])

    openings: list[Opening] = []
    for (xi0, xi1) in _runs(gap_col):
        width = float(xe[xi1 + 1] - xe[xi0])

        # Onko aukon sisällä lainkaan dataa? (skannaamaton seinänpätkä ≠ aukko,
        # paitsi jos pää on ankkuroitu nurkkaan jolloin sekin on uskottava oviaukko)
        run_has_data = bool(col_has_data[xi0:xi1 + 1].any())

        if not (_MIN_W <= width <= _MAX_W):
            _dbg(wall, width, 0, z0, floor_z, "width")
            continue
        if width > length * _MAX_FRACTION:
            _dbg(wall, width, 0, z0, floor_z, f"frac w/L={width/length:.2f}")
            continue

        # Reunaehto: materiaalia molemmin puolin TAI pää ankkuroitu nurkkaan
        at_start = xi0 <= x_lo + 1
        at_end = xi1 >= x_hi - 1
        left_ok = (not at_start) or (start_anchor and xi0 <= x_lo + 2)
        right_ok = (not at_end) or (end_anchor and xi1 >= x_hi - 2)
        # Sisäaukolle (ei seinän päässä) vaadi solidia naapuria heti vieressä
        if not at_start:
            left_ok = left_ok and bool(col_floor_solid[max(0, xi0 - _NEIGHBOR_COLS):xi0].any())
        if not at_end:
            right_ok = right_ok and bool(col_floor_solid[xi1 + 1:xi1 + 1 + _NEIGHBOR_COLS].any())
        if not (left_ok and right_ok):
            _dbg(wall, width, 0, z0, floor_z,
                 f"sides L={left_ok} R={right_ok} atS={at_start} atE={at_end}")
            continue

        # Seinänpään aukko ilman dataa = todennäköisesti skannaamaton → hylkää,
        # paitsi jos selvästi ankkuroitu nurkkaan (oviaukko).
        if not run_has_data and not (at_start and start_anchor) and not (at_end and end_anchor):
            _dbg(wall, width, 0, z0, floor_z, "no-data end")
            continue

        # Sill + korkeus: aukon sisäsarakkeiden Z-profiili. Käytä aukon keskisarakkeita.
        # row_occ vaatii että pinta kattaa OSAN aukon leveydestä (oikea sokkeli/lintel
        # ulottuu yli aukon; yksittäinen kalustepiste ei) → robusti clutterille.
        cx0 = xi0 + max((xi1 - xi0) // 4, 0)
        cx1 = xi1 - max((xi1 - xi0) // 4, 0) + 1
        inner = occ[cx0:cx1]                       # (cols, n_z)
        row_occ = inner.mean(axis=0) >= 0.5        # ≥50 % sisäsarakkeista täynnä
        # sill = korkein yhtenäinen pohjalta alkava pinta (esim. ikkunan sokkeli)
        z = 0
        while z < n_z and row_occ[z]:
            z += 1
        sill_row = z
        sill_z = float(ze[sill_row])
        sill_h = max(sill_z - floor_z, 0.0)

        # Head = aukon yläreuna. Aukon yli pinta palaa (lintel) → etsi seuraava
        # yhtenäinen pinta sill_row:n yläpuolelta; jos ei löydy → kattoon asti.
        head_row = n_z
        z = sill_row
        while z < n_z and not row_occ[z]:
            z += 1
        # z = ensimmäinen pinnallinen rivi sillin yläpuolella, tai n_z
        head_row = z
        head_z = float(ze[min(head_row, n_z)])
        # Jos aukko ulottuu lähelle seinän yläreunaa (ei lintel-pintaa) → kattoon
        if head_row >= wall_top_row - 1:
            head_z = wall_top_z

        height = head_z - sill_z
        if height < _MIN_H:
            _dbg(wall, width, height, sill_z, floor_z, "too-short")
            continue
        # Rajaa korkeus uskottavaan (täyskorkea oviaukko = lattiasta kattoon)
        height = min(height, wall.height)

        otype = _classify(sill_h, width, height)
        if otype == "unknown":
            _dbg(wall, width, height, sill_z, floor_z, f"unknown sill={sill_h:.0f}")
            continue
        _dbg(wall, width, height, sill_z, floor_z,
             f"ACCEPT {otype} atS={at_start} atE={at_end} data={run_has_data}")
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


def _classify(sill_h: float, width: float, height: float) -> str:
    # Ovi: lattiatason sill (matala) + uskottava korkeus. Leveys saa olla kapeahko
    # (kapea ovi / läpikäynti) kunhan se ei ole sokkelillinen ikkuna.
    if sill_h < _DOOR_SILL_MAX and height >= 1500.0:
        if width <= _DOOR_MAX_W:
            return "door"
        return "window"  # lattiasta lähtevä mutta hyvin leveä = lasiseinä/ikkuna
    # Ikkuna: kohonnut sill
    if sill_h >= _DOOR_SILL_MAX:
        return "window"
    # Matala lattiatason rako (height < 1500) = epävarma → hylkää
    return "unknown"

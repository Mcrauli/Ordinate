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
_WELL_COVERED_CONF = 0.5          # peitto ≥ tämä = aito seinä, säilytä vaikka suht.conf jäisi
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

    # Confidence-kynnys (toissijainen). Adaptiivinen suht.kynnys aliarvioi ISON
    # skenen aidot sisäseinät (koko-suhteinen conf romahtaa), joten seinä säilyy
    # myös jos se on tiheästi katettu pituudeltaan (conf = peitto ≥ 0.5, ks.
    # wall_ransac._axis_coverage). OR-ehto vain LISÄÄ seiniä, ei pudota mitään.
    if walls:
        max_conf = max(w.confidence for w in walls)
        conf_threshold = max_conf * 0.30
        walls = [w for w in walls
                 if w.confidence >= conf_threshold or w.confidence >= _WELL_COVERED_CONF]

    # Minimipituus
    walls = [w for w in walls if _wall_length(w) >= _MIN_WALL_LENGTH]

    # Deduplointi — yhdistä lähes samat seinät
    return _deduplicate(walls)


_COLIN_ANGLE_DEG = 8.0     # ° — collinear-yhdistyksen kulmatoleranssi
_COLIN_PERP_MM = 130.0     # mm — saman linjan kohtisuora toleranssi
_COLIN_GAP_MM = 450.0      # mm — vierekkäisten päiden max väli (pieni: ei yhdistä eri seiniä)
_COLIN_PERIM_ANGLE_DEG = 5.0   # ° — perimetrijatke: mitatun linjan adoptio kiertää
                               # kauimman pään; pitkällä jatkeella iso kulma heittäisi
_COLIN_PERIM_PERP_MM = 220.0   # mm — perimetriakselin tunnettu bias: kontuurigrid
                               # (max 90mm korjaus) + 300mm-swellin akselisiirto
                               # (~100mm) → sama fyysinen seinä voi olla ~175mm sivussa


def merge_collinear_walls(walls: list[Wall]) -> list[Wall]:
    """Yhdistä collinear vierekkäiset seinät yhdeksi (sama fyysinen seinä jaettuna).

    Kontuuridetektori jakaa pitkän seinän joskus kahteen pätkään eri paksuudella
    (esim. wall_002 120mm + wall_010 300mm pää-päähän → 300 on mittausartefakti).
    Sama linja (kulma+kohtisuora etäisyys) + päät lähekkäin → yksi seinä, paksuus =
    OHUEMPI (artefaktit ovat aina paisutettuja, ei koskaan ohennettuja)."""
    if len(walls) < 2:
        return walls
    work = list(walls)
    merged = True
    while merged:
        merged = False
        n = len(work)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = work[i], work[j]
                da, db = _direction(a), _direction(b)
                ang = np.degrees(np.arccos(min(1.0, abs(float(np.dot(da, db))))))
                if ang > _COLIN_ANGLE_DEG:
                    continue
                # Perimetrijatke: fiktio-perimetriseinä joka jatkaa MITATTUA seinää
                # samalla linjalla mutta biasoituneella akselilla (kontuurigrid +
                # paksuus-swell) → sulauta MITATUN seinän linjalle, älä pidemmän.
                # Muuten pinnat jäävät sisäkkäin nurkkaan (arkkitehti joutuu korjaamaan).
                fa = getattr(a.source, "method", "") == "floorplan"
                fb = getattr(b.source, "method", "") == "floorplan"
                if fa != fb:
                    meas, per = (b, a) if fa else (a, b)
                    dm = _direction(meas)
                    p0m = np.array(meas.axis[0], float)
                    nm = np.array([-dm[1], dm[0]])
                    offs = [abs(float(np.dot(np.array(p, float) - p0m, nm)))
                            for p in per.axis]
                    if ang <= _COLIN_PERIM_ANGLE_DEG and max(offs) <= _COLIN_PERIM_PERP_MM:
                        ts = [float(np.dot(np.array(p, float) - p0m, dm))
                              for p in (*meas.axis, *per.axis)]
                        tm0, tm1 = sorted(ts[:2]); tp0, tp1 = sorted(ts[2:])
                        gap = max(tm0, tp0) - min(tm1, tp1)
                        if gap <= _COLIN_GAP_MM:
                            lo = min(tm0, tp0); hi = max(tm1, tp1)
                            s = p0m + lo * dm; e = p0m + hi * dm
                            work[i] = meas.model_copy(update={
                                "axis": [[round(float(s[0]), 1), round(float(s[1]), 1)],
                                         [round(float(e[0]), 1), round(float(e[1]), 1)]],
                            })
                            work.pop(j)
                            merged = True
                            break
                p0a = np.array(a.axis[0], float); p1a = np.array(a.axis[1], float)
                p0b = np.array(b.axis[0], float); p1b = np.array(b.axis[1], float)
                na = np.array([-da[1], da[0]])
                perp = abs(float(np.dot(p0b - p0a, na)))
                if perp > _COLIN_PERP_MM:
                    continue
                # projektiot a:n suuntaan → tarkista vierekkäisyys (gap pieni / overlap)
                ts = [float(np.dot(p - p0a, da)) for p in (p0a, p1a, p0b, p1b)]
                ta0, ta1 = sorted(ts[:2]); tb0, tb1 = sorted(ts[2:])
                gap = max(ta0, tb0) - min(ta1, tb1)  # >0: väli, <0: overlap
                if gap > _COLIN_GAP_MM:
                    continue
                # yhdistä: span min..max a:n suunnassa, paksuus = ohuempi
                lo = min(ta0, tb0); hi = max(ta1, tb1)
                s = p0a + lo * da; e = p0a + hi * da
                keep = a if _wall_length(a) >= _wall_length(b) else b
                thin = a if a.thickness <= b.thickness else b
                work[i] = keep.model_copy(update={
                    "axis": [[round(float(s[0]), 1), round(float(s[1]), 1)],
                             [round(float(e[0]), 1), round(float(e[1]), 1)]],
                    "thickness": thin.thickness,
                    "measured_thickness": getattr(thin, "measured_thickness", None),
                })
                work.pop(j)
                merged = True
                break
            if merged:
                break
    return work


_BRIDGE_MIN_GAP = 300.0     # mm — kapeampi railo on nurkkasnapin heiniä, ei ovi
_BRIDGE_MAX_GAP = 2200.0    # mm — levein oviaukko (pariovi ~1900 + karmivara)
_BRIDGE_PERP = 25.0         # mm — sama linja: pintalukitut pätkät samasta seinästä
                            # ovat mm-tasolla; GT-pohjat porrastavat seinälinjaa 60mm
                            # (jog) — porrastetut EIVÄT ole sama seinä (merge → 64mm virhe)
_BRIDGE_BIN = 100.0         # mm — railon kattavuusbinit
_BRIDGE_LINTEL_FRAC = 0.6   # ylityksen katettava ≥ tämä osuus railosta


def bridge_lintel_gaps(walls: list[Wall], pts: np.ndarray) -> list[Wall]:
    """Silloita oviaukon katkaisema seinä: pystymaski pudottaa oviaukon kohdan
    (ei seinää 0–2 m) → kontuuri tuottaa kaksi kollineaarista pätkää joiden
    väliin ovi jää — eikä aukkodetektio etsi seinäjänteiden ULKOpuolelta.
    Oven päällä on aina ylitys (palkki ~2 m → katto): jos railon yllä on
    ylitysevidenssi, railo on saman seinän aukko → pätkät yhdistetään ja
    aukkodetektio luokittelee aukon normaalisti. Lattiakaistaa EI tutkita:
    suljettu ovilehti täyttää sen (synteettiset scenet skannataan ovet kiinni,
    lehti ±50 mm akselista) eikä ohuella seinällä lehteä voi erottaa pinnasta."""
    if len(walls) < 2 or len(pts) == 0:
        return walls
    work = list(walls)
    merged = True
    while merged:
        merged = False
        n = len(work)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = work[i], work[j]
                if len(a.axis) < 2 or len(b.axis) < 2:
                    continue
                da, db = _direction(a), _direction(b)
                ang = np.degrees(np.arccos(min(1.0, abs(float(np.dot(da, db))))))
                if ang > _COLIN_ANGLE_DEG:
                    continue
                p0a = np.array(a.axis[0], float); p1a = np.array(a.axis[1], float)
                p0b = np.array(b.axis[0], float); p1b = np.array(b.axis[1], float)
                na = np.array([-da[1], da[0]])
                if abs(float(np.dot(p0b - p0a, na))) > _BRIDGE_PERP:
                    continue
                ts = [float(np.dot(p - p0a, da)) for p in (p0a, p1a, p0b, p1b)]
                ta0, ta1 = sorted(ts[:2]); tb0, tb1 = sorted(ts[2:])
                gap_lo = min(ta1, tb1); gap_hi = max(ta0, tb0)
                gap = gap_hi - gap_lo
                if not (_BRIDGE_MIN_GAP <= gap <= _BRIDGE_MAX_GAP):
                    continue
                if not _gap_has_lintel(p0a, da, na, gap_lo, gap_hi, a, pts):
                    continue
                # Pintakoherenssi: pätkien SKANNATTUJEN pintojen on oltava samalla
                # tasolla — akselipäät voivat sattua lähelle vaikka seinälinja
                # porrastuu (GT-jog 60mm → yhdistetty seinä olisi 64mm pielessä).
                if not _segments_coplanar(p0a, da, na, (ta0, ta1), (tb0, tb1), a, pts):
                    continue
                lo = min(ta0, tb0); hi = max(ta1, tb1)
                s = p0a + lo * da; e = p0a + hi * da
                keep = a if _wall_length(a) >= _wall_length(b) else b
                thin = a if a.thickness <= b.thickness else b
                work[i] = keep.model_copy(update={
                    "axis": [[round(float(s[0]), 1), round(float(s[1]), 1)],
                             [round(float(e[0]), 1), round(float(e[1]), 1)]],
                    "thickness": thin.thickness,
                    "measured_thickness": getattr(thin, "measured_thickness", None),
                })
                work.pop(j)
                merged = True
                break
            if merged:
                break
    return work


_BRIDGE_COPLANAR_MM = 15.0  # mm — pätkien pintamediaanien max ero


def _segments_coplanar(p0a, da, na, span_a, span_b, wall, pts: np.ndarray) -> bool:
    rel = pts[:, :2] - p0a
    t = rel @ da
    perp = rel @ na
    z = pts[:, 2]
    zm = (z > wall.z_min + 200.0) & (z < wall.z_min + wall.height - 200.0)
    band = float(wall.thickness) / 2.0 + 80.0
    meds = []
    for lo, hi in (span_a, span_b):
        m = zm & (t > lo + 100.0) & (t < hi - 100.0) & (np.abs(perp) < band)
        if m.sum() < 100:
            return False
        s = perp[m]
        side = s > 0
        dom = s[side] if side.sum() >= (~side).sum() else s[~side]
        meds.append(float(np.median(dom)))
    return abs(meds[0] - meds[1]) <= _BRIDGE_COPLANAR_MM


def _gap_has_lintel(p0a, da, na, gap_lo, gap_hi, wall, pts: np.ndarray) -> bool:
    rel = pts[:, :2] - p0a
    t = rel @ da
    perp = rel @ na
    z = pts[:, 2]
    in_gap = (t > gap_lo) & (t < gap_hi) & (np.abs(perp) < 150.0)
    top = wall.z_min + wall.height
    lintel = in_gap & (z > wall.z_min + 1800.0) & (z < top + 100.0)
    nbins = max(int((gap_hi - gap_lo) / _BRIDGE_BIN), 1)
    edges = np.linspace(gap_lo, gap_hi, nbins + 1)
    lint_cov, _ = np.histogram(t[lintel], bins=edges)
    lint_frac = float((lint_cov >= 3).sum()) / nbins
    return lint_frac >= _BRIDGE_LINTEL_FRAC


def _deduplicate(walls: list[Wall]) -> list[Wall]:
    """Poistaa lähes päällekkäiset seinät — pitää pisimmän jänteen."""
    kept: list[Wall] = []
    used = [False] * len(walls)
    # Pidä PISIN jänne: lyhyt korkean confidencen fragmentti ei saa syrjäyttää
    # koko seinää (kadonnut jänne ei korjaannu; lateraalisijainti korjataan
    # myöhemmin pintalukituksessa). Lähes yhtä pitkien kesken korkein confidence,
    # sitten OHUEMPI (perimetri-swell paisuttaa saman seinän paksuudeksi esim.
    # 266mm vaikka pinta on 77mm). Pituus pyöristetään 500mm-koreihin jottei
    # 1mm ero ratkaise.
    walls_sorted = sorted(
        walls, key=lambda w: (-round(_wall_length(w) / 500.0), -w.confidence, w.thickness)
    )
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


_DANGLING_MAX_LEN = 2500.0   # mm — tätä pidempi kelluva seinä on aito detektio, ei tynkä
                             # (esim. seinä jonka naapurit jäivät vajaiksi — nurkkien
                             # sulku yhdistää sen myöhemmin; poisto hävittäisi oikean seinän)


_DANGLING_REACH = 2300.0   # mm — sama kuin corner_snap._CLOSE_MAX_EXT: näin kauas
                           # close_open_corners voi vielä yhdistää avoimen pään


_SCAN_RANGE_MM = 12000.0   # mm — kauempana KAIKISTA skannereista oleva seinä on
                           # harvan reunapilven (ajautuma/stray) artefakti, ei aito.
                           # TLS/Matterport kaappaa seinän luotettavasti ~≤10 m; 12 m
                           # antaa marginaalin. Mitattu Matterport-lobbylla: aidot
                           # seinät ≤7 m lähimmästä skannerista, artefaktit ≥12 m.


def remove_walls_beyond_scan_range(walls: list[Wall], scanner_origins: list,
                                   max_dist: float = _SCAN_RANGE_MM) -> list[Wall]:
    """Poista seinät jotka ovat kauempana kuin ``max_dist`` KAIKISTA skannereista.

    Käyttää E57:n skannerisijainteja kuten okkluusiosuodatin: aidot seinät
    skannataan läheltä, kaukana harvassa pilvessä oleva "seinä" on ajautuma-/
    stray-artefakti. No-op jos skannerisijainteja ei ole (esim. synteettinen tai
    metatiedoton pilvi) → ei koskaan poista mitään ilman todistetta."""
    if not scanner_origins:
        return walls
    S = np.array([np.asarray(o, float)[:2] for o in scanner_origins])
    kept: list[Wall] = []
    for w in walls:
        if len(w.axis) < 2:
            kept.append(w)
            continue
        a = np.asarray(w.axis[0], float); b = np.asarray(w.axis[1], float)
        ab = b - a
        denom = float(np.dot(ab, ab))
        if denom < 1e-9:
            dmin = float(np.min(np.linalg.norm(S - a, axis=1)))
        else:
            t = np.clip((S - a) @ ab / denom, 0.0, 1.0)   # lähin piste janalla
            proj = a + t[:, None] * ab
            dmin = float(np.min(np.linalg.norm(S - proj, axis=1)))
        if dmin <= max_dist:
            kept.append(w)
    return kept


def remove_dangling_walls(walls: list[Wall], free_tol: float = 400.0) -> list[Wall]:
    """Poistaa irralliset tynkäseinät: sisäseinä jonka jompikumpi pää on ilmassa
    (>free_tol kaikista muista seinistä) ei rajaa huonetta → roskaa. Perimetri
    (method=floorplan) ja pitkät seinät (≥ _DANGLING_MAX_LEN) säilytetään aina.
    Pää ei ole irrallinen jos seinän jatke osuu toiseen seinään ≤_DANGLING_REACH
    päässä — close_open_corners yhdistää sen myöhemmin (naapurin detektio voi
    olla vajaa vaikka seinä itse on aito)."""
    if len(walls) < 2:
        return walls
    kept: list[Wall] = []
    for i, w in enumerate(walls):
        if w.source.method == "floorplan":  # perimetriseinä → säilytä
            kept.append(w)
            continue
        if _wall_length(w) >= _DANGLING_MAX_LEN:
            kept.append(w)
            continue
        if len(w.axis) < 2:
            kept.append(w)
            continue
        others = [o for j, o in enumerate(walls) if j != i and len(o.axis) >= 2]
        d = _direction(w)
        free_ends = 0
        for e in (0, 1):
            ep = np.array(w.axis[e], float)
            dmin = min((_pt_seg_dist(ep, np.array(o.axis[0], float), np.array(o.axis[1], float))
                        for o in others), default=1e9)
            if dmin > free_tol and not _end_reaches_wall(ep, d if e == 1 else -d, others):
                free_ends += 1
        # Vain aidosti kelluvat (MOLEMMAT päät irti) poistetaan — huonejakaja
        # yhdistyy vähintään toisesta päästä, joten se säilyy.
        if free_ends < 2:
            kept.append(w)
    return kept


def _end_reaches_wall(ep: np.ndarray, out_dir: np.ndarray, others: list[Wall]) -> bool:
    for o in others:
        a = np.array(o.axis[0], float)
        b = np.array(o.axis[1], float)
        do = b - a
        Lo = float(np.linalg.norm(do))
        if Lo < 1.0:
            continue
        do /= Lo
        cross = float(out_dir[0] * do[1] - out_dir[1] * do[0])
        if abs(cross) < 0.35:   # ~kohtisuoruus, sama raja kuin _CLOSE_PERP_COS
            continue
        rel = a - ep
        s = float(rel[0] * do[1] - rel[1] * do[0]) / cross
        t = float(rel[0] * out_dir[1] - rel[1] * out_dir[0]) / cross
        if -120.0 <= s <= _DANGLING_REACH and -120.0 <= t <= Lo + 120.0:
            return True
    return False


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
    index = None
    if len(pts) >= 300_000 and len(walls) >= 3:
        from scan2bim.core.geometry.xy_index import XYIndex  # noqa: PLC0415
        index = XYIndex(pts)
    return [_refine(wall, pts, index) for wall in walls]


def _refine(wall: Wall, pts: np.ndarray, index=None) -> Wall:
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

    margin = 200.0
    if index is not None:
        from scan2bim.core.geometry.xy_index import subset  # noqa: PLC0415
        pts, _ = subset(pts, index, mid, along, normal, _MAX_SEARCH_DIST,
                        -(length / 2.0 + margin), length / 2.0 + margin)
        if len(pts) < _MIN_PEAK_PTS * 2:
            return wall

    xy = pts[:, :2]
    proj_along = (xy - mid) @ along
    proj_normal = (xy - mid) @ normal

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


_SKIN_MIN = 15.0      # mm — tätä lähempänä on sama pinta kahtena, ei oma seinä
_SKIN_MAX = 150.0     # mm — ohuempi kuin ohuinkin seinä (66 mm) + mittausvara


def remove_shelf_front_walls(walls, dist_lo=300.0, dist_hi=1500.0,
                             ang_tol_deg=12.0, min_partner_len=4000.0,
                             len_ratio=2.0, min_overlap_frac=0.5, retail=False):
    """Poista lattia-katto-hyllykön etupintaan syntyneet valeseinät.

    Liiketilan hyllykön etupinta ulottuu lattiasta kattoon → geometrisesti seinä,
    ja semanttinen suodatin ei sitä poista (etupinta on tiheä pystytaso). Erotin:
    hyllyn etupinta on LYHYEHKÖ seinä joka kulkee rinnakkain ja 300-1500 mm irti
    PALJON PIDEMMÄSTÄ seinästä (rakennuksen perimetri, jonka edessä hylly seisoo),
    peittäen sitä pituudeltaan. Oikea perimetriseinä on itse pisin → sillä ei ole
    pidempää rinnakkaista. Kontuurista riippumaton (raaka lattiakontuuri on 25-90 mm
    epätarkka → sitä ei saa käyttää). Mitattu synteettisellä myymälällä: hyllyn
    etupinnat 842-982 mm pidemmän perimetriseinän edessä; oikeat seinät eivät.

    ``retail=True`` (vain liiketilassa, ``_looks_like_retail``) lisää KOKO SEINÄN
    MITTAISEN hyllyn erottimen: len_ratio-testi ei nappaa hyllyä joka on yhtä pitkä
    kuin perimetri (histogrammidetektori löytää molemmat pintoina). Silloin hylly =
    seinä jonka ULKOPUOLELLA (rakennuksen reunaa kohti) on pitkä rinnakkainen
    perimetriseinä 300-1500 mm. Portitettu retailiin: asunnossa aito seinä voi olla
    lähellä ulkoseinää (komero/erkkeri) → ei saa poistaa siellä."""
    def _endpoints(w):
        return np.asarray(w.axis[0], float), np.asarray(w.axis[1], float)

    lens = []
    mids = []
    for w in walls:
        a, b = _endpoints(w)
        lens.append(float(np.linalg.norm(b - a)))
        mids.append(0.5 * (a + b))
    centroid = np.mean(mids, axis=0) if mids else np.zeros(2)

    remove = set()
    for i, w in enumerate(walls):
        Li = lens[i]
        if Li < 1e-6:
            continue
        a, b = _endpoints(w)
        u = (b - a) / Li
        n = np.array([-u[1], u[0]])
        c = 0.5 * (a + b)
        # W:n ULKOSUUNTA = normaali joka osoittaa poispäin rakennuksen keskeltä
        n_out = n if float(np.dot(c - centroid, n)) > 0 else -n
        for j, w2 in enumerate(walls):
            if j == i:
                continue
            Lj = lens[j]
            long_partner = Lj >= max(min_partner_len, len_ratio * Li)
            # retail: koko-mittainen hylly → kumppanin riittää olla pitkä perimetri
            full_len_ok = retail and Lj >= min_partner_len
            if not (long_partner or full_len_ok):
                continue
            a2, b2 = _endpoints(w2)
            L2v = b2 - a2
            u2 = L2v / Lj
            if abs(float(np.dot(u, u2))) < np.cos(np.radians(ang_tol_deg)):
                continue  # ei rinnakkainen
            # kohtisuora etäisyys w:n keskeltä kumppanin linjaan
            perp = abs(float(np.dot(c - a2, n)))
            # Seinää VASTEN liimattu hyllyskini: mitattu synteettisellä
            # myymälällä 32–33 mm perimetristä, eli ohuempi kuin ohuinkin
            # seinä (66 mm). `dist_lo` on 300 mm siksi, ettei saman seinän
            # kahta pintaa luettaisi hyllyksi — se raja jättää skinin
            # kokonaan sääntöjen ulkopuolelle (kirjattu AGENTS.md:hen auki
            # olevaksi puutteeksi). Vain liiketilassa: asunnossa aito seinä
            # voi olla lähellä ulkoseinää.
            is_skin = retail and _SKIN_MIN <= perp <= _SKIN_MAX
            if not (is_skin or dist_lo <= perp <= dist_hi):
                continue
            # w:n on peityttävä kumppanin pituudelle (kulkee sen vieressä)
            ta = float(np.dot(a - a2, u2)); tb = float(np.dot(b - a2, u2))
            lo, hi = sorted((ta, tb))
            ov = max(0.0, min(hi, Lj) - max(lo, 0.0))
            if ov / Li < min_overlap_frac:
                continue
            if long_partner:
                remove.add(i)
                break
            # full_len_ok: kumppanin oltava W:n ULKOPUOLELLA (perimetri hyllyn takana)
            if float(np.dot(0.5 * (a2 + b2) - c, n_out)) > 0:
                remove.add(i)
                break
    return [w for k, w in enumerate(walls) if k not in remove]


_SUP_THR = 0.15            # mitattu pintatuki: alle tämän pinnalla ei ole tukea
_PRUNE_CONT = 0.15         # jatkuvuus vyötäröllä — alle tämän ei ole yhtenäinen seinä
_PRUNE_OFFSET = 250.0      # mm — tätä kauempana oleva pinta = seinä on SIIRTYNYT, ei valhe
_PRUNE_MIN_LEN = 4000.0    # mm — lyhyt seinä ei voi todistaa palkkilinjaa
_PRUNE_MIN_NB = 10         # pistettä ±1 m vyötäröllä: alle tämän paikka on tyhjä


def _waist_neighbours(w, pts) -> int | None:
    """Pisteitä ±1000 mm seinästä vyötärökorkeudella — onko täällä MITÄÄN.

    Tämä erottaa haamun harvasta skannista ilman tiheyskynnystä: mitattu
    Rohbaulla, että perimetrihaamuilla luku on 0 JOKA tiheydellä, kun aidoilla
    lyhyillä seinillä se on 63 754 / 46 581 täydellä pilvellä ja yhä 36 / 27
    kun pilvi on harvennettu 1/2500:aan.
    """
    if pts is None or len(pts) == 0 or len(w.axis) < 2:
        return None
    p0 = np.array(w.axis[0], float)
    p1 = np.array(w.axis[1], float)
    L = float(np.linalg.norm(p1 - p0))
    if L < 1.0 or w.height < 1.0:
        return None
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    rel = pts[:, :2] - p0
    t, perp, z = rel @ u, rel @ n, pts[:, 2]
    sel = ((t > 0.0) & (t < L) & (np.abs(perp) < _SNAP_SEEK)
           & (z > w.z_min + 0.30 * w.height) & (z < w.z_min + 0.70 * w.height))
    return int(sel.sum())


def _axis_length(w) -> float:
    if len(w.axis) < 2:
        return 0.0
    return float(np.linalg.norm(np.array(w.axis[1], float) - np.array(w.axis[0], float)))


def prune_unsupported_walls(model, cloud=None) -> list[str]:
    """Poista seinät joilla ei ole yhtenäistä pintaa EIKÄ siirtynyttä vastinetta.

    Histogrammidetektori tekee palkiston keskikorkeuden tiheydestä pitkiä
    "seiniä". Mitattu Rohbau-GT:llä: niiden jatkuvuus on 0.053–0.070 ja lähin
    pinta 14–108 mm päässä (= palkin oma pinta), kun aidot seinät ovat
    0.50–1.00. Poisto maksoi kattavuutta 0.796 → 0.792 ja nosti tarkkuuden
    0.510 → 0.918.

    LYHYTTÄ seinää ei poisteta (`_PRUNE_MIN_LEN`, 4 m) JOS sillä on lainkaan
    pintatukea: siinä on liian vähän 500 mm sarakkeita jotta jatkuvuus
    todistaisi kumpaankaan suuntaan, ja palkkilinjat ovat aina pitkiä
    (Rohbaussa 28 m). Mitattu: harvennussarjassa 1/2500 poistui kaksi GT-aitoa
    lyhyttä seinää (2.0 m ja 1.0 m). Suoja EI koske täysin tyhjää seinää
    (`support == 0`) — Rohbaun 3.0 m ja 2.0 m perimetrihaamut ovat lyhyitä,
    ja niiden pinnalla ei ole yhtään pistettä.

    Siirtymärajan takia AITO seinä väärässä paikassa EI poistu: kauppakeskuksen
    `wall_ext_010` on GT-seinä 375 mm sivussa → jää tarkistuslistalle. Raja
    pitää vain jos `support_offset` on mitattu vyötäröltä — koko korkeudelta
    haettuna lattian roina antoi haamullekin offsetin ja suojasi sen.
    Palauttaa poistettujen id:t. Aukot siivotaan mukana, muuten IFC:hen jäisi
    aukkoja joiden seinää ei ole.
    """
    pts = np.asarray(cloud.points) if cloud is not None else None
    drop = []
    for w in model.walls:
        if w.continuity is None:
            # Mittaamattomuus EI ole todiste tuesta: jatkuvuus jää mittaamatta
            # juuri silloin kun vyötäröllä ei ole pisteitä, eli seinä jolla on
            # VÄHITEN evidenssiä pääsi portista läpi (Rohbau wall_ext_002:
            # tuki 0.022 ja 0.034, QA merkitsi molemmat väärän luokan seiniksi).
            # Lyhyttä seinää tämä ei silti tuomitse — `support` ja naapurimäärä
            # ovat molemmat tiheysriippuvaisia ja harva 1 m seinä saa matalat
            # arvot ilman että siinä on mitään vikaa. Yli 4 m matkalla
            # pisteiden puuttuminen vyötäröltä on itsessään mittaustulos.
            if _axis_length(w) < _PRUNE_MIN_LEN:
                continue
        elif w.continuity >= _PRUNE_CONT:
            continue
        if w.support_offset is not None and w.support_offset >= _PRUNE_OFFSET:
            continue
        if _axis_length(w) < _PRUNE_MIN_LEN:
            nb = _waist_neighbours(w, pts)
            # Täysin tyhjä seinä on tyhjä vaikka sen VIERESSÄ olisi pisteitä:
            # naapurit ovat lattiaa ja kalustetta, eivät tämän seinän pintaa.
            if w.support is not None and w.support <= 0.0:
                pass
            elif nb is None:
                if w.support:
                    continue
            elif nb >= _PRUNE_MIN_NB:
                continue
        drop.append(w.id)
    if not drop:
        return []
    gone = set(drop)
    model.walls = [w for w in model.walls if w.id not in gone]
    model.openings = [o for o in model.openings if o.wall_id not in gone]
    return drop


_SNAP_SEEK = 1000.0        # mm — kuinka kaukaa siirtynyttä vastinetta etsitään
_SNAP_BAND = 60.0          # mm — kaista huipun ympärillä
_SNAP_MIN_CONT = 0.80      # vastineen jatkuvuus: alle tämän ei ole seinä vaan sirpale
_SNAP_MIN_SHIFT = 30.0     # mm — pienempi siirto kuuluu pintalukitukselle
_SNAP_MIN_COLS = 8         # sarakkeita (= 4 m) jotta jatkuvuus todistaa jotain
_SNAP_MIN_GAIN = 0.10      # siirto hyväksytään vain jos MITATTU tuki paranee tällä
_SNAP_PAIR_TOL = 80.0      # mm — kuinka tarkasti vastapinnan on oltava paksuuden päässä
_SNAP_MAX_SUP = 0.50       # yli puoliksi keilattu pinta on jo oikeassa paikassa


def snap_displaced_walls(model, cloud) -> list[tuple[str, float]]:
    """Siirrä pinnattomat seinät mitatulle pinnalle. Palauttaa (id, siirto mm).

    Ehto on `support < 0.50`, ei `== 0`: mitattu aulassa, jossa `wall_007`:n
    oikea pinta on 842 mm sivussa mutta mallin pinnalla sattuu olemaan
    hajapisteitä (tuki 0.17) — siirtyneisyys ei katoa siitä että seinää
    raapaisee jokin. Yli puoliksi keilattu pinta on jo oikeassa paikassa.
    Varsinaisen päätöksen tekevät jatkuvuus- ja siirtoehdot alla: oikeassa
    paikassa oleva seinä löytää huipun omalta pinnaltaan, jolloin siirto jää
    alle `_SNAP_MIN_SHIFT`:n eikä mitään tapahdu.

    `support == 0` ei kerro onko kyse haamusta vai aidosta seinästä väärässä
    paikassa. Ero on mitattavissa: aidolla on vyötärökorkeudella YHDENSUUNTAINEN
    ja JATKUVA vastine (kauppakeskuksen 99.8 m ulkoseinä: 388 mm, jatkuvuus
    1.00), haamulla ei ole mitään (Rohbaun perimetritynkät: ei vastinetta
    ±1000 mm). Siirto tehdään vain kun vastine on lähes koko pituudelta, joten
    sirpale ei vedä seinää mukanaan.

    LYHYTTÄ seinää ei siirretä lainkaan (`_SNAP_MIN_COLS`, 4 m): 500 mm
    sarakkeilla metrin seinään mahtuu kaksi saraketta, jolloin jatkuvuusehto
    täyttyy millä tahansa läiskällä. Mitattu Rohbaulla: GT-aito 1.0 m
    `wall_ext_011` hyppäsi 400 mm ja sen oma tuki putosi 0.212 → 0.155
    (kattavuus 0.792 → 0.749, tarkkuus 0.918 → 0.905).

    Tämä on eri asia kuin `_align_faces_to_surface_median`, joka hienosäätää jo
    ~oikeassa paikassa olevaa seinää 25 mm katolla. Tässä seinä on satoja
    millejä pielessä, eikä nykyinen sijainti ole menettämisen arvoinen.
    """
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return []
    moved: list[tuple[str, float]] = []
    for w in model.walls:
        if getattr(w, "support", None) is None or w.support >= _SNAP_MAX_SUP or len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], float)
        p1 = np.array(w.axis[1], float)
        L = float(np.linalg.norm(p1 - p0))
        if L < 1.0 or w.height < 1.0:
            continue
        u = (p1 - p0) / L
        n = np.array([-u[1], u[0]])
        rel = pts[:, :2] - p0
        t = rel @ u
        perp = rel @ n
        z = pts[:, 2]
        sel = ((t > 0.0) & (t < L) & (np.abs(perp) < _SNAP_SEEK)
               & (z > w.z_min + 0.30 * w.height) & (z < w.z_min + 0.70 * w.height))
        if sel.sum() < 200:
            continue
        tp, pp = t[sel], perp[sel]
        hist, edges = np.histogram(pp, bins=80, range=(-_SNAP_SEEK, _SNAP_SEEK))
        peak = 0.5 * (edges[hist.argmax()] + edges[hist.argmax() + 1])
        on = np.abs(pp - peak) < _SNAP_BAND
        if on.sum() < 100:
            continue
        ncol = max(1, int(L / 500.0))
        if ncol < _SNAP_MIN_COLS:
            continue
        ci = np.clip((tp[on] / L * ncol).astype(np.int64), 0, ncol - 1)
        from scan2bim.core.qa.deviation import _column_continuity  # noqa: PLC0415
        if _column_continuity(np.bincount(ci, minlength=ncol)) < _SNAP_MIN_CONT:
            continue
        # Kaksipuolinen seinä: jos vastapinta löytyy ~paksuuden päästä, akseli
        # kuuluu pintojen PUOLIVÄLIIN. Muuten mallin väärä pinta osuisi lähimmälle
        # keilatulle pinnalle ja seinä jäisi kokonaisen paksuuden verran sivuun.
        rest = pp[~on]
        peak2 = None
        if len(rest) > 100:
            h2, e2 = np.histogram(rest, bins=80, range=(-_SNAP_SEEK, _SNAP_SEEK))
            cand = 0.5 * (e2[h2.argmax()] + e2[h2.argmax() + 1])
            if (abs(abs(cand - peak) - w.thickness) < _SNAP_PAIR_TOL
                    and int((np.abs(rest - cand) < _SNAP_BAND).sum()) >= 100):
                peak2 = float(cand)
        if peak2 is not None:
            shift = 0.5 * (float(peak) + peak2)
        else:
            shift = float(peak) - np.sign(peak) * (w.thickness / 2.0)
        if abs(shift) < _SNAP_MIN_SHIFT:
            continue
        d = n * shift
        new_axis = [[float(p0[0] + d[0]), float(p0[1] + d[1])],
                    [float(p1[0] + d[0]), float(p1[1] + d[1])]]
        # Ratkaiseva ehto: siirto hyväksytään vain jos se PARANTAA mitattua
        # tukea. Pelkkä "lähin tiheä huippu" ei riitä — Rohbaun GT-aito 28 m
        # `wall_008` (tuki 0.372) löysi huipun 138 mm sivusta ja siirtyi pois
        # oikealta paikaltaan (kattavuus 0.792 → 0.748). Tuki mitataan samasta
        # pilvestä molemmissa asennoissa, joten vertailu on suora.
        from scan2bim.core.qa.deviation import _wall_support  # noqa: PLC0415
        probe = w.model_copy(deep=True)
        probe.axis = new_axis
        after = _wall_support(probe, pts, None)
        if after is None or after[0] < w.support + _SNAP_MIN_GAIN:
            continue
        w.axis = new_axis
        moved.append((w.id, shift))
    return moved

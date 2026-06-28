"""Kulmakorjaus: yhdistää seinät kulmiin snäppäämällä ja jatkamalla akseleita.

Kaksivaiheinen:
  1) pairwise extend/snap — jatka/snäppää akselin päät risteyksiin (lähikulmat).
  2) corner-resolve — rakenna KAIKKI seinä-seinä-risteykset ja vedä jokainen
     seinän pää lähimpään pätevään risteykseen: ylittävä pää TRIMMATAAN, vajaa
     pää JATKETAAN. Tämä poistaa tyngät (overshoot) ja sulkee raot.
"""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import Wall

_MAX_EXTEND = 1300.0      # mm — kuinka paljon seinää voidaan jatkaa leikkauspisteeseen
_MAX_SNAP   = 700.0       # mm — T-liitoksen snap-etäisyys (leikkauspiste seinän sisällä)
_PARALLEL_COS_MAX = 0.70  # |cos| > tämä → rinnakkaiset, ohitetaan


def snap_corners(walls: list[Wall]) -> list[Wall]:
    """Snäppää ja jatkaa seinäakseleita leikkauspisteisiin."""
    if len(walls) < 2:
        return walls

    axes: list[list[list[float]]] = [[list(w.axis[0]), list(w.axis[1])] for w in walls]
    n = len(walls)
    for i in range(n):
        for j in range(i + 1, n):
            _try_connect(axes, i, j)

    _resolve_corners(axes)

    return [walls[i].model_copy(update={"axis": axes[i]}) for i in range(n)]


# --- vajaiden nurkkien sulku: vain AVOIMET päät, vain toisiinsa -----------------
# Iso extend _resolve_corners:issa gridaa (venyttää SISÄseiniä kaukaisiin
# risteyksiin). Tämä on turvallinen: käsittelee VAIN avoimia päitä (>_OPEN_TOL
# kaikista seinistä) ja yhdistää avoimen pään VAIN toiseen avoimeen päähän niiden
# kohtisuorien linjojen leikkaukseen. Sisäseinillä ei ole avoimia päitä → ei gridiä.
_OPEN_TOL = 60.0          # mm — pää on "avoin" jos näin kaukana lähimmästä seinästä
_CLOSE_MAX_EXT = 2300.0   # mm — avoimen pään saa jatkaa korkeintaan tämän verran nurkkaan
_CLOSE_PERP_COS = 0.35    # |cos| < tämä → riittävän kohtisuorat muodostamaan nurkan


def close_open_corners(walls: list[Wall]) -> list[Wall]:
    """Sulje vajaat nurkat: yhdistä parit avoimia päitä niiden linjojen leikkaukseen."""
    if len(walls) < 2:
        return walls
    axes = [[list(w.axis[0]), list(w.axis[1])] for w in walls]
    n = len(walls)
    P = [(np.array(a[0], float), np.array(a[1], float)) for a in axes]
    dirs, lens = [], []
    for a, b in P:
        d = b - a
        L = float(np.linalg.norm(d))
        lens.append(L)
        dirs.append(d / L if L > 1 else None)

    def nearest_other(p, i):
        return min(
            (_pt_seg_dist(p, P[j][0], P[j][1]) for j in range(n) if j != i and dirs[j] is not None),
            default=1e9,
        )

    # avoimet päät
    open_ends = []
    for i in range(n):
        if dirs[i] is None:
            continue
        for e in (0, 1):
            if nearest_other(P[i][e], i) > _OPEN_TOL:
                open_ends.append((i, e))

    used = set()
    for idx_a in range(len(open_ends)):
        ia, ea = open_ends[idx_a]
        if (ia, ea) in used:
            continue
        best = None
        for idx_b in range(idx_a + 1, len(open_ends)):
            ib, eb = open_ends[idx_b]
            if (ib, eb) in used or ib == ia:
                continue
            if abs(float(np.dot(dirs[ia], dirs[ib]))) > _CLOSE_PERP_COS:
                continue  # ei kohtisuorat → ei nurkka
            pt, _, _ = _intersection_params(P[ia][0], dirs[ia], P[ib][0], dirs[ib])
            if pt is None:
                continue
            ea_pt = np.array(axes[ia][ea], float)
            eb_pt = np.array(axes[ib][eb], float)
            da = float(np.linalg.norm(pt - ea_pt))
            db = float(np.linalg.norm(pt - eb_pt))
            if da > _CLOSE_MAX_EXT or db > _CLOSE_MAX_EXT:
                continue
            score = da + db
            if best is None or score < best[0]:
                best = (score, idx_b, pt)
        if best is not None:
            _, idx_b, pt = best
            ib, eb = open_ends[idx_b]
            axes[ia][ea] = [round(float(pt[0]), 1), round(float(pt[1]), 1)]
            axes[ib][eb] = [round(float(pt[0]), 1), round(float(pt[1]), 1)]
            used.add((ia, ea))
            used.add((ib, eb))

    # PASS 2: vielä avoimet päät → venytä kohtisuoran OLEMASSA olevan seinän linjalle,
    # MUTTA vain jos leikkaus osuu sen janalle (t∈[0,L], pieni marginaali) → aito
    # T-liitos, ei kaukainen gridiviiva. Vain avoin pää liikkuu.
    for i, e in open_ends:
        if (i, e) in used or dirs[i] is None:
            continue
        ep = np.array(axes[i][e], float)
        if nearest_other(ep, i) <= _OPEN_TOL:
            continue
        best = None
        for j in range(n):
            if j == i or dirs[j] is None:
                continue
            if abs(float(np.dot(dirs[i], dirs[j]))) > _CLOSE_PERP_COS:
                continue
            pt, _, tj = _intersection_params(P[i][0], dirs[i], P[j][0], dirs[j])
            if pt is None:
                continue
            if tj < -120.0 or tj > lens[j] + 120.0:   # leikkaus janan ULKONA → hylkää (ei gridiä)
                continue
            ext = float(np.linalg.norm(pt - ep))
            if ext > _CLOSE_MAX_EXT:
                continue
            if best is None or ext < best[0]:
                best = (ext, pt)
        if best is not None:
            axes[i][e] = [round(float(best[1][0]), 1), round(float(best[1][1]), 1)]
            used.add((i, e))

    return [walls[i].model_copy(update={"axis": axes[i]}) for i in range(n)]


def _pt_seg_dist(p, a, b) -> float:
    ab = b - a
    L = float(ab @ ab)
    if L < 1.0:
        return float(np.linalg.norm(p - a))
    t = max(0.0, min(1.0, float((p - a) @ ab) / L))
    return float(np.linalg.norm(p - (a + t * ab)))


def _try_connect(axes: list[list[list[float]]], i: int, j: int) -> None:
    p0a = np.array(axes[i][0], dtype=float)
    p1a = np.array(axes[i][1], dtype=float)
    p0b = np.array(axes[j][0], dtype=float)
    p1b = np.array(axes[j][1], dtype=float)

    da = p1a - p0a
    db = p1b - p0b
    len_a = float(np.linalg.norm(da))
    len_b = float(np.linalg.norm(db))
    if len_a < 1.0 or len_b < 1.0:
        return

    ua = da / len_a
    ub = db / len_b

    if abs(float(np.dot(ua, ub))) > _PARALLEL_COS_MAX:
        return

    pt, ta, tb = _intersection_params(p0a, ua, p0b, ub)
    if pt is None:
        return

    # --- Seinä A ---
    # ta < 0:       leikkauspiste p0a:n takana → jatka p0a
    # ta > len_a:   leikkauspiste p1a:n edessä → jatka p1a
    # muuten:       T-liitos, snäppää B:n lähin pääte; leikkaa A:n pää liitokseen jos lähellä
    if ta < 0 and abs(ta) <= _MAX_EXTEND:
        axes[i][0] = _fmt(pt)
    elif ta > len_a and (ta - len_a) <= _MAX_EXTEND:
        axes[i][1] = _fmt(pt)
    else:
        # T-liitos A:ssa — snäppää B:n lähin pääte kohtisuoraan A:han
        _snap_endpoint_to_wall(axes, j, p0a, ua, len_a)

    # --- Seinä B ---
    if tb < 0 and abs(tb) <= _MAX_EXTEND:
        axes[j][0] = _fmt(pt)
        # T-liitos A:ssa ja B:n pää on juuri liitoksen vieressä → leikkaa A:n ylijäämä
        if abs(tb) < 10.0 and 0.0 < ta < len_a:
            _clip_overshoot(axes, i, ta, len_a, pt)
    elif tb > len_b and (tb - len_b) <= _MAX_EXTEND:
        axes[j][1] = _fmt(pt)
        if abs(tb - len_b) < 10.0 and 0.0 < ta < len_a:
            _clip_overshoot(axes, i, ta, len_a, pt)
    else:
        _snap_endpoint_to_wall(axes, i, p0b, ub, len_b)


_MAX_OVERSHOOT = 100.0  # mm — seinän pää saa ylittää T-liitoksen enintään tämän verran


def _clip_overshoot(
    axes: list[list[list[float]]],
    k: int,
    ta: float,
    len_a: float,
    pt: np.ndarray,
) -> None:
    """Leikkaa seinän k pään T-liitospisteeseen jos se ylittää sen enintään _MAX_OVERSHOOT."""
    p0_near = len_a - ta  # etäisyys p1:een
    p1_near = ta           # etäisyys p0:aan
    if p0_near <= _MAX_OVERSHOOT and p0_near >= 0.0:
        axes[k][1] = _fmt(pt)
    elif p1_near <= _MAX_OVERSHOOT and p1_near >= 0.0:
        axes[k][0] = _fmt(pt)


# --- corner-resolve: vedä jokainen pää lähimpään pätevään risteykseen ---------
#
# Tynkä (overshoot) = pää joka jatkuu kohtisuoran seinän OHI; rako = pää joka jää
# vajaaksi. Molemmat korjautuvat samalla logiikalla: etsi seinän jokaiselle
# päälle lähin risteys jonka SE seinä leikkaa, ja vedä pää siihen — kunhan se on
# sallitun ikkunan sisällä eikä lyhennä seinää nollaan.

_RES_TRIM = 600.0        # mm — pään saa vetää SISÄÄN (trimmaus) enintään tämän verran
_RES_EXTEND = 1300.0     # mm — pään saa vetää ULOS (jatko) enintään tämän verran
_RES_PERP_MAX = 250.0    # mm — risteys kelpaa vain jos kohtisuora seinä kulkee näin läheltä päätä
_RES_MIN_LEN = 250.0     # mm — älä lyhennä seinää tätä lyhyemmäksi


def _resolve_corners(axes: list[list[list[float]]]) -> None:
    """Vedä jokainen seinän pää lähimpään pätevään seinä-seinä-risteykseen.

    Pätevä risteys päälle E (E ∈ {0,1}):
      - kohtisuora kumppani (|cos| <= _PARALLEL_COS_MAX)
      - risteys osuu kumppanin janalle (sallien pieni ylitys) → aito kulma/T
      - risteyksen along-koordinaatti tällä seinällä on lähellä päätä E:
          ylitys (trimmaus)  : risteys ennen päätä,   <= _RES_TRIM
          vajaa  (jatko)     : risteys pään takana,   <= _RES_EXTEND
      - lopputulos ei lyhennä seinää alle _RES_MIN_LEN
    Valitaan kullekin päälle along-suunnassa LÄHIN pätevä risteys.
    """
    n = len(axes)
    dirs: list[np.ndarray | None] = []
    lens: list[float] = []
    p0s: list[np.ndarray] = []
    for k in range(n):
        p0 = np.array(axes[k][0], dtype=float)
        p1 = np.array(axes[k][1], dtype=float)
        d = p1 - p0
        ln = float(np.linalg.norm(d))
        p0s.append(p0)
        lens.append(ln)
        dirs.append((d / ln) if ln >= 1.0 else None)

    new_ends: list[list[np.ndarray | None]] = [[None, None] for _ in range(n)]

    for i in range(n):
        ui = dirs[i]
        Li = lens[i]
        if ui is None or Li < 1.0:
            continue
        p0 = p0s[i]
        # ehdokkaat kummallekin päälle: (|delta|, along_t, piste)
        best = [None, None]  # type: ignore
        best_d = [1e18, 1e18]

        for j in range(n):
            if j == i:
                continue
            uj = dirs[j]
            Lj = lens[j]
            if uj is None or Lj < 1.0:
                continue
            if abs(float(np.dot(ui, uj))) > _PARALLEL_COS_MAX:
                continue
            pt, ti, tj = _intersection_params(p0, ui, p0s[j], uj)
            if pt is None:
                continue
            # risteyksen oltava kumppanin janalla (aito kulma/T, ei kaukainen jatke)
            if tj < -_RES_PERP_MAX or tj > Lj + _RES_PERP_MAX:
                continue
            # kumman pään lähellä risteys on?
            for E in (0, 1):
                end_t = 0.0 if E == 0 else Li
                delta = ti - end_t  # >0: risteys pään ULKOPUOLELLA (jatko); <0: SISÄPUOLELLA (trim)
                if E == 0:
                    # p0: jatko = risteys ennen p0 (delta<0), trim = risteys p0:n jälkeen (delta>0)
                    extend = -delta  # mm ulospäin
                    trim = delta     # mm sisäänpäin
                else:
                    # p1: jatko = risteys p1:n jälkeen (delta>0), trim = risteys ennen p1 (delta<0)
                    extend = delta
                    trim = -delta
                if extend > _RES_EXTEND or trim > _RES_TRIM:
                    continue
                if extend < 0 and trim < 0:
                    continue
                # tarkista ettei lyhennä seinää liikaa
                if E == 0:
                    new_len = Li - ti
                else:
                    new_len = ti
                if new_len < _RES_MIN_LEN:
                    continue
                dist = abs(ti - end_t)
                if dist < best_d[E]:
                    best_d[E] = dist
                    best[E] = pt
        new_ends[i][0] = best[0]
        new_ends[i][1] = best[1]

    # sovita lasketut päät (vain jos molemmat eivät romahda samaan pisteeseen)
    for i in range(n):
        for E in (0, 1):
            pt = new_ends[i][E]
            if pt is not None:
                axes[i][E] = _fmt(pt)


def _snap_endpoint_to_wall(
    axes: list[list[list[float]]],
    k: int,
    wall_origin: np.ndarray,
    wall_dir: np.ndarray,
    wall_len: float,
) -> None:
    """Snäppää seinän k lähin pääte kohtisuoraan seinä-viivalle (T-liitos)."""
    _TOL = 50.0
    for idx in range(2):
        ep = np.array(axes[k][idx], dtype=float)
        t = float(np.dot(ep - wall_origin, wall_dir))
        if t < -_TOL or t > wall_len:
            continue
        t = max(0.0, t)
        proj = wall_origin + t * wall_dir
        dist = float(np.linalg.norm(ep - proj))
        if dist <= _MAX_SNAP:
            axes[k][idx] = _fmt(proj)
            return


def _intersection_params(
    p1: np.ndarray, d1: np.ndarray,
    p2: np.ndarray, d2: np.ndarray,
) -> tuple[np.ndarray | None, float, float]:
    """Palauttaa (leikkauspiste, ta, tb). None jos rinnakkaiset."""
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
    b = np.array([p2[0] - p1[0], p2[1] - p1[1]])
    det = float(np.linalg.det(A))
    if abs(det) < 1e-6:
        return None, 0.0, 0.0
    ts = np.linalg.solve(A, b)
    ta, tb = float(ts[0]), float(ts[1])
    return p1 + ta * d1, ta, tb


def _fmt(pt: np.ndarray) -> list[float]:
    return [round(float(pt[0]), 1), round(float(pt[1]), 1)]

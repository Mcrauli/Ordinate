"""Ortogonaalinen suoristus (Manhattan-world).

Asunnot ovat lähes aina suorakulmaisia, mutta keilaus tuottaa seinät pienessä
(usein satunnaisessa) kierrossa ja kukin seinä hieman eri kulmassa. Tämä etsii
pistepilven yhden hallitsevan kiertokulman ja snäppää jokaisen seinän lähimpään
kahdesta kohtisuorasta suunnasta (θ tai θ+90°). Vain ±tol asteen sisällä olevat
suoristetaan — selvästi vinot seinät (esim. viistot) jätetään rauhaan.

Sisään: list[Wall] → ulos: list[Wall] (akselit kierretty keskipisteen ympäri).
"""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import Wall

_SNAP_TOL_DEG = 22.0   # ° — tätä lähempänä perhesuuntaa olevat snäpätään


def _wall_angle(wall: Wall) -> float | None:
    p0, p1 = np.array(wall.axis[0]), np.array(wall.axis[1])
    d = p1 - p0
    if float(np.hypot(d[0], d[1])) < 1.0:
        return None
    return float(np.arctan2(d[1], d[0]))


def dominant_angle(walls: list[Wall]) -> float | None:
    """Hallitseva kiertokulma [0, π/2), pituuspainotettu ympyräkeskiarvo.

    Kahden kohtisuoran perheen suunnat osuvat samaan arvoon mod 90°, joten
    kulma kerrotaan 4:llä (jakso π/2 → 2π) ympyräkeskiarvoa varten.
    """
    sin_sum = cos_sum = 0.0
    for w in walls:
        a = _wall_angle(w)
        if a is None:
            continue
        length = float(np.hypot(w.axis[1][0] - w.axis[0][0], w.axis[1][1] - w.axis[0][1]))
        sin_sum += length * np.sin(4.0 * a)
        cos_sum += length * np.cos(4.0 * a)
    if sin_sum == 0.0 and cos_sum == 0.0:
        return None
    return float(np.arctan2(sin_sum, cos_sum) / 4.0)


def regularize_orthogonal(walls: list[Wall], drop_skew: bool = True) -> list[Wall]:
    """Snäppää seinät kahteen kohtisuoraan suuntaan keskipisteen ympäri.

    Asunto on Manhattan-world: seinä joka jää yli _SNAP_TOL_DEG päähän
    molemmista perhesuunnista on virhedetektio (vino roskaseinä) ja
    pudotetaan kun ``drop_skew``.
    """
    if len(walls) < 2:
        return walls
    theta = dominant_angle(walls)
    if theta is None:
        return walls

    tol = np.radians(_SNAP_TOL_DEG)
    out: list[Wall] = []
    for w in walls:
        a = _wall_angle(w)
        if a is None:
            out.append(w)
            continue
        # Kandidaattisuunnat: θ, θ+90°, θ+180°, θ+270° (akseli on suuntaamaton)
        best_dir = None
        best_diff = tol
        for k in range(4):
            cand = theta + k * (np.pi / 2.0)
            diff = abs(_angle_wrap(a - cand))
            if diff < best_diff:
                best_diff = diff
                best_dir = cand
        if best_dir is None:
            if not drop_skew:
                out.append(w)  # liian vino → ei snäppiä
            continue           # drop_skew: pudota vino roskaseinä

        p0 = np.array(w.axis[0], dtype=float)
        p1 = np.array(w.axis[1], dtype=float)
        mid = 0.5 * (p0 + p1)
        half = 0.5 * float(np.linalg.norm(p1 - p0))
        u = np.array([np.cos(best_dir), np.sin(best_dir)])
        n0 = mid - half * u
        n1 = mid + half * u
        out.append(w.model_copy(update={"axis": [
            [round(float(n0[0]), 1), round(float(n0[1]), 1)],
            [round(float(n1[0]), 1), round(float(n1[1]), 1)],
        ]}))
    return out


def _angle_wrap(a: float) -> float:
    """Kääri kulma välille [-π, π]."""
    return float((a + np.pi) % (2.0 * np.pi) - np.pi)


# --- per-seinä hienokierto ---------------------------------------------------
# Globaali snäppi antaa yhden rectilineaarisen kulman koko pohjalle, mutta
# todellinen ruudukko on usein 1–2° vinossa siihen nähden, ja pitkän (7 m) seinän
# pää ajautuu 100–200 mm. Korjaus: kierrä jokaista seinää keskipisteensä ympäri
# enintään ±_FINE_MAX_DEG niin että sen OMAT pinnan pisteet asettuvat akselin
# suuntaisiksi (kohtisuora hajonta minimiin). Pieni raja pitää pohjan suorana
# eikä riko nurkkien snäppäystä.

_FINE_MAX_DEG = 2.5        # ° — suurin sallittu poikkeama globaalista akselista.
                           # Tätä suurempi vaadittu kierto = epäluotettava sovitus
                           # (T-liitos/viisto) → seinä hylätään (ei clampata).
_FINE_BAND = 100.0         # mm — kohtisuora kaista jolta seinän omat pisteet haetaan
_FINE_MIN_PTS = 300        # min pisteitä jotta kierretään
_FINE_END_MARGIN = 200.0   # mm — jätä päät pois (nurkka/T-liitos sotkee suunnan)


def fine_rotate_walls(
    walls: list[Wall],
    pts: np.ndarray,
    z_min: float | None = None,
    z_max: float | None = None,
    max_dev_deg: float = _FINE_MAX_DEG,
) -> list[Wall]:
    """Kierrä jokaista seinää keskipisteensä ympäri parhaiten omiin pisteisiinsä.

    Käytetään globaalin snäpin JÄLKEEN: poistaa pitkän seinän pään ajautuman
    sovittamalla seinän suunnan sen dominantin skannatun pinnan pistejoukkoon.
    Kierto rajataan ±``max_dev_deg`` jotta pohja pysyy rectilineaarisena.
    """
    if pts is None or len(pts) == 0 or len(walls) < 1:
        return walls

    xy = np.asarray(pts)[:, :2]
    z = np.asarray(pts)[:, 2] if pts.shape[1] > 2 else None
    max_dev = np.radians(max_dev_deg)

    out: list[Wall] = []
    for w in walls:
        rotated = _fine_rotate_wall(w, xy, z, z_min, z_max, max_dev)
        out.append(rotated)
    return out


def _fine_rotate_wall(w: Wall, xy, z, z_min, z_max, max_dev: float) -> Wall:
    p0 = np.array(w.axis[0], dtype=float)
    p1 = np.array(w.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    # Vain riittävän pitkät seinät: lyhyissä pään ajautuma on pieni mutta niiden
    # kiertäminen tekee niistä ei-yhdensuuntaisia naapureihin → valehuoneita.
    # Sliver-suodatus huonedetektiossa tekee 1.5m-rajan turvalliseksi (lisää voittoa
    # keskipitkiltä seiniltä) — valehuoneet hylätään aspect/min-width-säännöllä.
    if length < 1500.0:
        return w

    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    mid = 0.5 * (p0 + p1)

    rel = xy - p0
    along_proj = rel @ along
    perp = rel @ normal

    mask = (
        (along_proj >= _FINE_END_MARGIN)
        & (along_proj <= length - _FINE_END_MARGIN)
        & (np.abs(perp) <= _FINE_BAND)
    )
    if z is not None and z_min is not None and z_max is not None:
        mask &= (z >= z_min) & (z <= z_max)
    if int(mask.sum()) < _FINE_MIN_PTS:
        return w

    band_along = along_proj[mask]
    band_perp = perp[mask]

    # Kaistalla on sisä- JA ulkopinta (yksi tai kaksi piikkiä). Sovita KUMPIKIN
    # pinta erikseen ja ota kulmakorjausten KESKIARVO → kierto keskilinjan
    # suuntaan, jolloin akseli pysyy kohtisuorassa MOLEMPIIN pintoihin ja paksuus
    # säilyy. (Yhden dominantin pinnan sovitus kiertäisi akselin sen pinnan
    # mukaan → toinen pinta vinoon → thickness_lock mittaa vinosti → paksuus pilalle.)
    from scipy.signal import find_peaks
    hist, edges = np.histogram(band_perp, bins=np.arange(-_FINE_BAND, _FINE_BAND + 10.0, 10.0))
    centers_h = 0.5 * (edges[:-1] + edges[1:])
    pks, _ = find_peaks(hist, height=max(hist.max() * 0.3, 5.0), distance=4)
    if len(pks) == 0:
        return w
    pks = sorted(pks, key=lambda p: hist[p], reverse=True)[:2]   # 1–2 vahvinta pintaa

    deltas = []
    for pidx in pks:
        pk_off = float(centers_h[pidx])
        surf = np.abs(band_perp - pk_off) <= 40.0
        if int(surf.sum()) < _FINE_MIN_PTS // 2:
            continue
        s_along = band_along[surf]
        s_perp = band_perp[surf]
        da = s_along - s_along.mean()
        dp = s_perp - s_perp.mean()
        saa = float(da @ da)
        if saa < 1e-6:
            continue
        d = float(np.arctan2(float(da @ dp), saa))
        resid = dp - (float(da @ dp) / saa) * da
        if len(resid) > 2 and float(np.sqrt(np.mean(resid ** 2))) > 35.0:
            continue   # hajanainen kaista (kalusteet/T-liitos) → älä luota tähän pintaan
        deltas.append(d)
    if not deltas:
        return w
    delta = float(np.mean(deltas))   # keskilinjan suunta = pintojen kulmien keskiarvo

    # Liian iso vaadittu kierto = ei-yhdensuuntainen pinta (T/viisto/naapuri) → hylkää.
    if abs(delta) > max_dev or abs(delta) < np.radians(0.05):
        return w

    c, s = np.cos(delta), np.sin(delta)
    u = np.array([c * along[0] - s * along[1], s * along[0] + c * along[1]])
    half = 0.5 * length
    n0 = mid - half * u
    n1 = mid + half * u
    return w.model_copy(update={"axis": [
        [round(float(n0[0]), 1), round(float(n0[1]), 1)],
        [round(float(n1[0]), 1), round(float(n1[1]), 1)],
    ]})

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

# Aidosti vino seinä (ei-Manhattan): regularize pakottaa sen ruudukkoon eikä
# ±2.5° hienokierto riitä palauttamaan. Skew-polku hyväksyy isomman kierron VAIN
# vahvalla evidenssillä: PCA-kulma leveästä kaistasta + verifiointi että kierron
# jälkeen pisteet muodostavat ohuen pinnan (kaluste/sotku ei muodosta).
_SKEW_MAX_DEG = 8.0        # ° — suurin hyväksyttävä aito vinous
_SKEW_MIN_DEG = 3.0        # ° — alle tämän hoitaa normaali hienokierto
_SKEW_RESID_MAX = 25.0     # mm — pinnan max RMS-hajonta kierron jälkeen
_SKEW_COVER_MIN = 0.55     # osuus kaistan pisteistä joiden on osuttava pinnoille


def _band_radius(length: float) -> float:
    """Laajin kohtisuora kaista jota kiertopolku voi kysyä (= `_try_skew_rotate`
    oletus `band_w`). Indeksihaun säde on tämä → osajoukko on YLIJOUKKO ja
    kutsuja soveltaa saman ehdon → valikoituva pistejoukko ja sen järjestys ovat
    täsmälleen samat kuin koko taulukkoa skannattaessa."""
    return _FINE_BAND + length * float(np.sin(np.radians(_SKEW_MAX_DEG)))


def _wall_band(xy, z, index, p0, along, normal, length):
    """(xy, z) vain seinän kaistalta. Ilman indeksiä koko taulukko."""
    if index is None:
        return xy, z
    sel = index.near_segment(p0, along, normal, _band_radius(length),
                             _FINE_END_MARGIN, length - _FINE_END_MARGIN)
    return xy[sel], (None if z is None else z[sel])


def fine_rotate_walls(
    walls: list[Wall],
    pts: np.ndarray,
    z_min: float | None = None,
    z_max: float | None = None,
    max_dev_deg: float = _FINE_MAX_DEG,
    index=None,
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
        rotated = _fine_rotate_wall(w, xy, z, z_min, z_max, max_dev, index)
        out.append(rotated)
    return out


def refine_skew_walls(
    walls: list[Wall],
    pts: np.ndarray,
    z_min: float | None = None,
    z_max: float | None = None,
    index=None,
) -> list[Wall]:
    """Toinen kiertopassi täysipitkillä akseleilla: palauta aidosti vinot seinät.

    Ensimmäinen fine_rotate ajaa ennen nurkkasnappia, jolloin vino seinä on usein
    lyhyt detektiopätkä (<1.5 m → ei kierretä lainkaan) ja regularize on lukinnut
    sen ruudukkoon. Tässä yritetään skew-polkua datasta käsin: grid-seinillä
    PCA-kulma jää alle kynnyksen eikä mitään tapahdu; aidosti vinolle seinälle
    kierto + 1–2 normaalia hienokiertoiteraatiota viimeistelevät kulman.
    Grid-seinien normaalikiertoa EI toisteta (iteroiva kierto ajautuu
    kalustetulla datalla — tunnettu ansa)."""
    if pts is None or len(pts) == 0 or not walls:
        return walls
    xy = np.asarray(pts)[:, :2]
    z = np.asarray(pts)[:, 2] if pts.shape[1] > 2 else None
    out: list[Wall] = []
    for w in walls:
        skewed = _skew_rotate_wall(w, xy, z, z_min, z_max, index=index)
        if skewed is w:
            out.append(w)
            continue
        # Jäännöskulman viimeistely VAIN skew-kierretyille: sama estimaattori
        # alennetulla kynnyksellä ja KAPEALLA kaistalla (leveä poimii verhot/
        # karmit ja laimentaa PCA:n). Grid-seiniä EI kierretä uudelleen —
        # kokeiltu ja MITATTU huonoksi (pinta 2.1→14.6 mm): ohut-pinta-
        # verifiointi läpäisee myös väärät pinnat (verho/komero on ohut pinta).
        for _ in range(3):
            polished = _skew_rotate_wall(
                skewed, xy, z, z_min, z_max, min_deg=0.3, band_w=1.5 * _FINE_BAND,
                index=index,
            )
            if polished.axis == skewed.axis:
                break
            skewed = polished
        out.append(skewed)
    return out


def _skew_rotate_wall(
    w: Wall, xy, z, z_min, z_max,
    min_deg: float | None = None, band_w: float | None = None,
    max_deg: float | None = None, index=None,
) -> Wall:
    p0 = np.array(w.axis[0], dtype=float)
    p1 = np.array(w.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 1500.0:
        return w
    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    mid = 0.5 * (p0 + p1)
    xy, z = _wall_band(xy, z, index, p0, along, normal, length)
    rel = xy - p0
    along_proj = rel @ along
    perp = rel @ normal
    if z is not None and z_min is not None and z_max is not None:
        zm = (z >= z_min) & (z <= z_max)
        along_proj = along_proj[zm]
        perp = perp[zm]
    return _try_skew_rotate(
        w, along, mid, length, along_proj, perp,
        min_deg=min_deg, band_w=band_w, max_deg=max_deg,
    )


def _fine_rotate_wall(w: Wall, xy, z, z_min, z_max, max_dev: float, index=None) -> Wall:
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

    xy, z = _wall_band(xy, z, index, p0, along, normal, length)
    rel = xy - p0
    along_proj = rel @ along
    perp = rel @ normal

    # Z-suodatus koskee myös skew-polkua: lattia/katto-pisteet kaistalla
    # hukuttaisivat pintaverifioinnin.
    if z is not None and z_min is not None and z_max is not None:
        zm = (z >= z_min) & (z <= z_max)
        along_proj = along_proj[zm]
        perp = perp[zm]

    mask = (
        (along_proj >= _FINE_END_MARGIN)
        & (along_proj <= length - _FINE_END_MARGIN)
        & (np.abs(perp) <= _FINE_BAND)
    )
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
        return _try_skew_rotate(w, along, mid, length, along_proj, perp)
    delta = float(np.mean(deltas))   # keskilinjan suunta = pintojen kulmien keskiarvo

    # Liian iso vaadittu kierto = ei-yhdensuuntainen pinta (T/viisto/naapuri) → hylkää
    # normaalipolulla; aidosti vino seinä yrittää vielä skew-polkua (vahva evidenssi).
    if abs(delta) > max_dev:
        return _try_skew_rotate(w, along, mid, length, along_proj, perp)
    if abs(delta) < np.radians(0.05):
        return w

    return _rotated(w, along, mid, length, delta)


def _rotated(w: Wall, along: np.ndarray, mid: np.ndarray, length: float, delta: float) -> Wall:
    c, s = np.cos(delta), np.sin(delta)
    u = np.array([c * along[0] - s * along[1], s * along[0] + c * along[1]])
    half = 0.5 * length
    n0 = mid - half * u
    n1 = mid + half * u
    return w.model_copy(update={"axis": [
        [round(float(n0[0]), 1), round(float(n0[1]), 1)],
        [round(float(n1[0]), 1), round(float(n1[1]), 1)],
    ]})


def _try_skew_rotate(
    w: Wall, along: np.ndarray, mid: np.ndarray, length: float,
    along_proj: np.ndarray, perp: np.ndarray,
    min_deg: float | None = None, band_w: float | None = None,
    max_deg: float | None = None,
) -> Wall:
    """Aidosti vinon seinän palautus. Vino seinä ajautuu pakotetusta akselista
    ±length/2·sin(θ) → normaali ±100mm-kaista leikkaa sen pään pois eikä
    pintasovitus näe kahta piikkiä. Tässä: (1) leveä kaista joka kattaa vinouden,
    (2) PCA-suora antaa kulman, (3) VERIFIOINTI: kierretyssä kehyksessä pisteiden
    on muodostettava 1–2 ohutta pintaa jotka kattavat ison osan kaistasta —
    kalusterivi tai sotku ei läpäise tätä."""
    # Kaistan katettava koko vinon seinän ajautuma (akseli voi olla sivussa
    # keskikohdastakin) → täysi span, ei puolikas.
    if band_w is None:
        band_w = _FINE_BAND + length * np.sin(np.radians(_SKEW_MAX_DEG))
    m = (
        (along_proj >= _FINE_END_MARGIN)
        & (along_proj <= length - _FINE_END_MARGIN)
        & (np.abs(perp) <= band_w)
    )
    if int(m.sum()) < _FINE_MIN_PTS:
        return w
    da = along_proj[m] - along_proj[m].mean()
    dp = perp[m] - perp[m].mean()
    saa = float(da @ da)
    if saa < 1e-6:
        return w
    delta = float(np.arctan2(float(da @ dp), saa))
    deg = abs(np.degrees(delta))
    lo = min_deg if min_deg is not None else _SKEW_MIN_DEG
    hi = max_deg if max_deg is not None else _SKEW_MAX_DEG
    if deg < lo or deg > hi:
        return w

    # Verifiointi kierretyssä kehyksessä: jäännöshajonnan on romahdettava pinnoiksi.
    resid = dp - (float(da @ dp) / saa) * da
    from scipy.signal import find_peaks
    hist, edges = np.histogram(resid, bins=np.arange(resid.min() - 10.0, resid.max() + 10.0, 10.0))
    if not len(hist):
        return w
    centers = 0.5 * (edges[:-1] + edges[1:])
    pks, _ = find_peaks(hist, height=max(hist.max() * 0.3, 5.0), distance=4)
    if not len(pks):
        return w
    pks = sorted(pks, key=lambda p: hist[p], reverse=True)[:2]
    covered = 0
    for pidx in pks:
        surf = np.abs(resid - float(centers[pidx])) <= 40.0
        n_surf = int(surf.sum())
        if n_surf < _FINE_MIN_PTS // 2:
            continue
        rms = float(np.sqrt(np.mean((resid[surf] - resid[surf].mean()) ** 2)))
        if rms > _SKEW_RESID_MAX:
            return w   # leveä möykky pinnan kohdalla → ei luotettava vino seinä
        covered += n_surf
    if covered < _SKEW_COVER_MIN * int(m.sum()):
        return w
    return _rotated(w, along, mid, length, delta)

"""Palkkidetektori: ALAPINTAKARTTA (soffit), ei pisteklusteri.

Vanha malli klusteroi kattokaistan pisteet XY:ssä ja luki palkin leveyden
klusterin XY-laajuudesta. Skannattu palkki ei ole umpikappale vaan kaksi
pystypintaa ja niiden välinen alapinta, joten klusterin leveys ei ole palkin
leveys: mitattu synteettisellä liiketilalla (`data/_beam_probe.py`) sama 300 mm
palkki antoi joko 143 mm (yksi pinta erillisenä klusterina) tai 47 000 mm (koko
palkisto ketjuuntui pilarien kautta yhdeksi klusteriksi). Molemmat hylättiin
leveysportissa, ja Rohbau3D:n GT:tä vasten koko detektori sai tarkkuuden 0.048
ja kattavuuden 0/77 (`data/_beam_qa.py`).

Uusi malli mittaa sen mitä keilain oikeasti näkee: jokaiselle XY-solulle
kattokaistan ALIN piste = sen kohdalla roikkuvan kappaleen alapinta.
Vierekkäiset samankorkeat solut ovat yksi alapintalaikku, ja laikun poikittainen
leveys ON palkin leveys.

Alapintaehto hoitaa myös erottelun ilman erillistä sääntöä: seinän, pilarin,
hyllykön ja gondolin alin piste on lattian lähellä, joten ne eivät koskaan
tuota alapintaa katon läheltä.
"""
from __future__ import annotations

import logging
import uuid

import numpy as np

from scan2bim.schemas.model import Beam, BeamProfile, ElementSource

log = logging.getLogger(__name__)

_CELL = 200.0            # mm — alapintakartan solu
_MIN_PTS = 3             # pistettä solussa jotta alapinta on mitattu
_SURF_MM = 60.0          # mm — pinnan paksuus: tämän sisällä olevat ovat samaa pintaa
_SURF_FRAC = 0.10        # osuus solun pisteistä jotka pinnan on kerättävä
_Z_TOL = 150.0           # mm — naapurisolu samaa laikkua jos alapinta tällä välillä
_MAX_DEPTH = 3000.0      # mm — tätä syvemmälle laatasta roikkuva ei ole palkki
_MAX_DEPTH_FRAC = 0.35   # …mutta korkeassa hallissa palkki on syvempi: raja on
                         # kumpi tahansa suurempi. Rohbau site_07:n palkit ovat
                         # 2.6 m syviä eli kiinni 3000 mm:n rajassa, joten
                         # kiinteä luku olisi pudottanut seuraavan hallin palkit
_MIN_DEPTH = 150.0       # mm — tätä matalampi ei erotu laatasta
_MIN_DEPTH_FRAC = 0.08   # …mutta korkeassa hallissa 460 mm alaslasku on ripa tai
                         # kanava, ei palkki: raja skaalautuu huonekorkeudella
_WALL_MARGIN = 250.0     # mm — seinälinjaa lähempänä oleva alapinta on seinän, ei palkin
_MIN_LENGTH = 1200.0     # mm
_MIN_ASPECT = 3.0        # pituus/leveys — alle tämän on pilari tai laatan pudotus
_MIN_FILL = 0.5          # laikun solut / suorakaiteen solut — palkin alapinta on
                         # täysi suorakaide; kulmassa kääntyvä kanava ei ole
_MAX_WIDTH = 3000.0      # mm — tätä leveämpi on alaslaskettu katto, ei palkki
_MAX_WIDTH_DEPTH = 2.0   # leveys/syvyys: kantava palkki on kapea ja syvä, kotelo
                         # leveä ja matala. Mitattu GT-palkeista 0.3–0.8 (Rohbau)
                         # ja 0.44 (liiketila); asunnon kotelo 2.6. Ks. `_patch_to_beam`.
_MIN_CELLS = 20

_OFF = 500_000           # solukoordinaatit positiivisiksi ennen avaimen laskua
_BASE = 1_000_003


def detect_beams(cloud, walls, floor_z: float, ceiling_z: float,
                 has_ceiling: bool = False) -> list[Beam]:
    """Alapintalaikut kattovyöhykkeessä -> palkit.

    `has_ceiling` on jäljellä kutsujien vuoksi eikä enää vaikuta: kattoon
    kiinnittymisen vaatimus poistettiin, koska se mittasi näkyvyyttä eikä
    kiinnitystä. Ks. `_patch_to_beam`.
    """
    pts = np.asarray(cloud.points, dtype=np.float64)
    height = ceiling_z - floor_z
    if len(pts) < _MIN_PTS or height < 1500.0:
        return []

    z_free = max(floor_z + 0.5 * height,
                 ceiling_z - max(_MAX_DEPTH, _MAX_DEPTH_FRAC * height))
    min_depth = _min_depth(height)
    cells = _soffit_cells(pts, floor_z + 200.0, ceiling_z - 30.0,
                          z_free, ceiling_z - min_depth)
    if walls:
        cells = _drop_wall_cells(cells, walls)
    if len(cells) < _MIN_CELLS:
        return []

    cand = []
    for comp in _patches(cells):
        b = _patch_to_beam(comp, cells, pts, ceiling_z, has_ceiling, min_depth)
        if b is not None:
            cand.append(b)
    beams = _merge_collinear(cand)
    for i, b in enumerate(beams):
        beams[i] = b.model_copy(update={"id": f"beam_{i:03d}"})
    log.info("BeamDetector: %d alapintalaikkua -> %d palkkia", len(cand), len(beams))
    return beams


# --------------------------------------------------------------------------- #

def _soffit_cells(pts: np.ndarray, z_lo: float, z_hi: float,
                  z_free: float, z_top: float) -> dict[int, tuple[float, int]]:
    """XY-solu -> (alapinta, pistemäärä).

    `z_free` on korkeus jonka yläpuolella alapinnan on oltava: sen alle yltävä
    kappale jatkuu lattiaa kohti eikä ole vapaa palkki. `z_top` estää katon
    oman pinnan menemästä laikuksi.
    """
    m = (pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)
    q = pts[m]
    if not len(q):
        return {}
    ij = np.floor(q[:, :2] / _CELL).astype(np.int64) + _OFF
    if ij.min() < 0 or ij.max() >= _OFF * 2:
        return {}
    key = ij[:, 0] * _BASE + ij[:, 1]
    order = np.argsort(key, kind="stable")
    key_s, z_s = key[order], q[order, 2]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(key_s)]])
    out: dict[int, tuple[float, int]] = {}
    for s, e in zip(starts, ends):
        if e - s < _MIN_PTS:
            continue
        zb = _surface_z(np.sort(z_s[s:e]))
        if zb != zb or zb < z_free or zb > z_top:
            continue
        out[int(key_s[s])] = (zb, int(e - s))
    return out


def _surface_z(z_sorted: np.ndarray) -> float:
    """Solun alin PINTA, ei alin piste. nan jos solussa ei ole pintaa.

    Minimi on tiheysmittari eikä geometriamittari: 200 mm solussa on 4 mm
    skannissa ~2500 pistettä ja 70 mm skannissa ~8, joten yksi harhapiste
    (putki, kaapeli, kohina) painaa solun alapinnan alas sitä varmemmin mitä
    tiheämpi skanni on. Ja koska `z_free`n alle painunut solu POISTETAAN
    kartasta, tiheys ei vain siirrä alapintaa vaan repii laikun palasiksi.

    Mitattu scene_07000 (`data/_beam_density.py`): sama scene, sama geometria,
    pelkkä tiheys eri — instanssikattavuus heitteli 0.000 ja 0.643 välillä ja
    HARVA pilvi voitti tiheän.

    Pinta = alin taso jonka ympärille `_SURF_MM`:n sisään kertyy `_SURF_FRAC`
    osuus solun OMISTA pisteistä. Osuus on tiheysriippumaton, pistemäärä ei.
    """
    n = len(z_sorted)
    need = max(_SURF_FRAC * n, 2.0)
    hi = np.searchsorted(z_sorted, z_sorted + _SURF_MM, side="right")
    ok = np.flatnonzero((hi - np.arange(n)) >= need)
    return float(z_sorted[ok[0]]) if len(ok) else float("nan")


def _cell_xy(keys: np.ndarray) -> np.ndarray:
    ij = np.stack([keys // _BASE, keys % _BASE], axis=1).astype(np.float64) - _OFF
    return ij * _CELL + _CELL / 2.0


def _drop_wall_cells(cells: dict, walls) -> dict:
    """Seinälinjalla oleva alapinta on seinän yläosa, ei palkki."""
    from .column_detector import _dist_to_walls

    keys = np.fromiter(cells.keys(), dtype=np.int64, count=len(cells))
    far = _dist_to_walls(_cell_xy(keys), walls) > _WALL_MARGIN
    return {int(k): cells[int(k)] for k, f in zip(keys, far) if f}


def _patches(cells: dict):
    """Yhtenäiset laikut: naapuri 4-yhteydessä, alapinta _Z_TOL:n sisällä.

    Ankkuriehto (ero myös laikun ensimmäiseen soluun) on pakollinen: ilman sitä
    laikku ryömii portaittain läpi koko mallin — mitattu 200 m "palkki".
    """
    seen: set[int] = set()
    for k0 in cells:
        if k0 in seen:
            continue
        z0 = cells[k0][0]
        stack, comp = [k0], []
        seen.add(k0)
        while stack:
            k = stack.pop()
            comp.append(k)
            i, j = divmod(k, _BASE)
            z = cells[k][0]
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (i + di) * _BASE + (j + dj)
                if n not in cells or n in seen:
                    continue
                zn = cells[n][0]
                if abs(zn - z) <= _Z_TOL and abs(zn - z0) <= _Z_TOL:
                    seen.add(n)
                    stack.append(n)
        if len(comp) >= _MIN_CELLS:
            yield comp


def _min_depth(height: float) -> float:
    """Kuinka syvälle laatasta on roikuttava jotta on palkki eikä ripa.

    Kiinteä 150 mm on oikein 2.7 m huoneessa ja väärin 10 m hallissa: siellä
    se päästi läpi 460–1700 mm syvät kattoripat ja kanavat, joiden alapinta
    (7100–7740) oli KAIKKIEN GT-palkkien yläpuolella (5176–6378).

    Mitattu (`data/_beam_depth_sweep.py`, pelkkä detektori, viisi Rohbau-sceneä
    + synteettinen liiketila): osuudella 0.08 instanssikattavuus säilyi
    JOKAISESSA aineistossa täsmälleen samana ja tarkkuus nousi 0.866→0.905,
    0.738→0.799, 0.744→0.850, 0.814→0.869, 0.876→0.877; liiketila ei muuttunut
    lainkaan. Osuudet 0.03 ja 0.05 eivät tuoneet mitään.
    """
    return max(_MIN_DEPTH, _MIN_DEPTH_FRAC * height)


def _patch_to_beam(comp: list[int], cells: dict, pts: np.ndarray,
                   ceiling_z: float, has_ceiling: bool,
                   min_depth: float = _MIN_DEPTH) -> Beam | None:
    """Laikku palkiksi, tai None jos jokin portti hylkää.

    Kiinnitysporttia EI ole: se vaati, ettei alapinnan ja laatan välissä ole
    300 mm tyhjää, mutta korkeassa tilassa lattialta keilattaessa palkin uuma
    jää katsomissuunnan taakse eikä sitä skannata lainkaan. Portti hylkäsi siis
    palkin siitä, ettei sitä nähdä — ei siitä, ettei se ole kiinni.

    Mitattu ablaationa (`data/_beam_attach_abl.py`, kaikki viisi Rohbau-sceneä,
    pelkkä detektori): portti päällä 39/77 instanssia tarkkuudella 0.824, pois
    62/77 tarkkuudella 0.808. Liiketila-S, liiketila-L ja asunto antoivat
    TÄSMÄLLEEN saman tuloksen kummallakin (`_beam_attach_abl2.py`), eli portti
    ei estänyt niissä mitään.

    Hinta: katosta roikkuva kanava valmiissa tilassa tulee nyt palkiksi, jos se
    läpäisee pituus-, leveys-, suhde- ja täyttöportit. Se on tiedossa ja
    testattu (`test_hanging_mep_becomes_a_beam_without_the_attachment_gate`).
    """
    xy = _cell_xy(np.asarray(comp, dtype=np.int64))
    z = np.array([cells[k][0] for k in comp], dtype=np.float64)
    c = xy.mean(axis=0)
    A = xy - c
    _, V = np.linalg.eigh(A.T @ A / len(A))
    u, n = V[:, 1], V[:, 0]
    s = A @ u
    t = A @ n
    length = float(s.ptp()) + _CELL
    width = float(t.ptp()) + _CELL
    if length < _MIN_LENGTH or width > _MAX_WIDTH:
        return None
    if length / width < _MIN_ASPECT:
        return None
    if len(comp) / ((length / _CELL) * (width / _CELL)) < _MIN_FILL:
        return None
    soffit = float(np.median(z))
    depth = ceiling_z - soffit
    if depth < min_depth:
        return None
    # Poikkileikkaus, ei pohjakuva. `_MIN_ASPECT` mittaa pituutta suhteessa
    # leveyteen eikä katso syvyyttä lainkaan, joten 3.1 m pitkä, 965 mm leveä
    # ja 373 mm syvä kotelo asunnon katonrajassa meni läpi (aspect 3.3).
    # Kantava palkki on kapea ja syvä. Mitattu (`data/_beam_profile_sweep.py`,
    # viisi Rohbau-sceneä + liiketila + asunto): kaikilla GT-aineistoilla
    # TÄSMÄLLEEN samat luvut jokaisella katolla 3.0 … 1.2 — kantaviin palkkeihin
    # tämä ei kosketa. Asunnon kotelo katoaa kun katto on 2.0 tai tiukempi.
    if _MAX_WIDTH_DEPTH and width > _MAX_WIDTH_DEPTH * depth:
        return None

    p0 = c + s.min() * u
    p1 = c + s.max() * u
    z_mid = soffit + depth / 2.0
    return Beam(
        id=str(uuid.uuid4()),
        confidence=round(min(1.0, len(comp) / 60.0), 3),
        source=ElementSource(method="soffit"),
        axis=[[round(float(p0[0]), 1), round(float(p0[1]), 1), round(z_mid, 1)],
              [round(float(p1[0]), 1), round(float(p1[1]), 1), round(z_mid, 1)]],
        profile=BeamProfile(width=round(width, 1), height=round(depth, 1)),
    )


def _in_box(xy: np.ndarray, c: np.ndarray, u: np.ndarray, n: np.ndarray,
            length: float, width: float) -> np.ndarray:
    d = xy - c
    return (np.abs(d @ u) <= length / 2.0) & (np.abs(d @ n) <= width / 2.0)


_MERGE_GAP = 1500.0      # mm — pilari katkaisee alapinnan; tätä isompi väli on eri palkki
_MERGE_ANGLE = 0.985     # cos 10°
_MERGE_OFFSET = 0.75     # osuus leveydestä — sivusiirtymä jonka jälkeen eri palkki


def _merge_collinear(beams: list[Beam]) -> list[Beam]:
    """Pilarien katkomat palkin pätkät yhdeksi palkiksi.

    Yhdistetään vain samansuuntaiset, samalla alapinnalla olevat ja saman
    linjan pätkät joiden väli on pienempi kuin pilarin leveysluokka — muuten
    tämä olisi sama ylivenytys jonka seinäpuolelta jouduttiin leikkaamaan pois.
    """
    out: list[Beam] = []
    for b in sorted(beams, key=lambda b: -_length(b)):
        for i, m in enumerate(out):
            j = _try_join(m, b)
            if j is not None:
                out[i] = j
                break
        else:
            out.append(b)
    return out


def _length(b: Beam) -> float:
    a = np.array(b.axis[0][:2])
    q = np.array(b.axis[1][:2])
    return float(np.linalg.norm(q - a))


def _try_join(m: Beam, b: Beam) -> Beam | None:
    a0 = np.array(m.axis[0][:2])
    a1 = np.array(m.axis[1][:2])
    b0 = np.array(b.axis[0][:2])
    b1 = np.array(b.axis[1][:2])
    la, lb = float(np.linalg.norm(a1 - a0)), float(np.linalg.norm(b1 - b0))
    if la < 1.0 or lb < 1.0:
        return None
    ua, ub = (a1 - a0) / la, (b1 - b0) / lb
    if abs(float(ua @ ub)) < _MERGE_ANGLE:
        return None
    if abs(m.axis[0][2] - b.axis[0][2]) > _Z_TOL:
        return None
    na = np.array([-ua[1], ua[0]])
    if max(abs(float((b0 - a0) @ na)),
           abs(float((b1 - a0) @ na))) > _MERGE_OFFSET * m.profile.width:
        return None
    s = [float((p - a0) @ ua) for p in (b0, b1)]
    lo, hi = min(s), max(s)
    if lo > la + _MERGE_GAP or hi < -_MERGE_GAP:
        return None
    p0 = a0 + ua * min(0.0, lo)
    p1 = a0 + ua * max(la, hi)
    z = m.axis[0][2]
    return m.model_copy(update={
        "axis": [[round(float(p0[0]), 1), round(float(p0[1]), 1), z],
                 [round(float(p1[0]), 1), round(float(p1[1]), 1), z]],
        "profile": BeamProfile(width=max(m.profile.width, b.profile.width),
                               height=max(m.profile.height, b.profile.height)),
        "confidence": round(min(1.0, m.confidence + b.confidence), 3),
    })

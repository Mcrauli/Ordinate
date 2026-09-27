"""Seinän TAKANA oleva rinnakkainen pinta — kontuurin katvealue.

`cv2.findContours` jäljittää vapaan tilan reunan, eli se näkee vain
ENSIMMÄISEN pinnan. Jos betoniperimetrin edessä seisoo kipsiseinä puolen
metrin päässä, vain toinen niistä päätyy malliin ja toinen katoaa kokonaan —
mikään detektorin kynnys ei auta, koska pinta on maskin sisällä.

Rohbau3D-GT:llä mitattuna tämä on suurin yksittäinen kattavuusvaje: 20.6 %:n
vajeesta yli puolet (52.6 %) istuu 400–700 mm päässä mallipinnasta, ja ne
pisteet ovat GT:ssä omia Drywall-instanssejaan.

Sisään: löydetyt seinät + pistepilvi → ulos: lisäseinät katvepinnoille.
Ehdokas joutuu todistamaan samat asiat kuin mikä tahansa aito seinä:
yhtenäisen pinnan vyötärökorkeudella ja massan suhteessa emäseinän omaan
pintaan (ei absoluuttista pistemäärää — putken on toimittava millä tahansa
keilaustiheydellä).
"""
from __future__ import annotations

import numpy as np

from ordinate.schemas.model import ElementSource, Wall

_SEEK = 1500.0             # mm — kuinka kauas seinän molemmin puolin katsotaan
_BIN = 50.0                # mm — poikkileikkaushistogrammin bini
_BAND = 60.0               # mm — kaista huipun ympärillä
_MIN_GAP = 250.0           # mm — näin kaukana mallipinnasta = ERI pinta, ei sama
_MIN_LEN = 8000.0          # mm — lyhyt seinä ei todista katvepintaa (ks. AGENTS.md)
_MIN_MASS = 0.10           # osuus emäseinän OMASTA pintamassasta
_MIN_CONT = 0.30           # sama jatkuvuusvaatimus kuin aidolla seinällä
_MAX_PER_WALL = 2          # useampi rinnakkaishuippu on kalustetta, ei seinää
_MIN_JUDGE = 10            # EI tiheyskynnys: alle tämän kaistassa ei ole mitään
_NEW_THICK = 120.0         # mm — vain toinen pinta näkyy → oletuspaksuus
_SHELF_BIN = 50.0          # mm — z-histogrammin bini hyllytasoja etsittäessä
_SHELF_PEAK_REL = 4.0      # taso = bini jossa tämä kerta keskiarvo (suhteellinen)
_SHELF_SEP = 300.0         # mm — tätä kauempana toisistaan = ERI taso
_SHELF_LEVELS = 3          # toistuvat tasot = hyllykkö, yksittäinen = palkki
_MIN_HEIGHT = 1000.0       # mm — matalampi pinta on kaluste, ei seinä
_MIN_H_FRAC = 0.20         # seinä ulottuu vähintään tämän osuuden kerroksesta
_SLAB_MARGIN = 300.0       # mm — lattia ja katto pois reunamittauksesta
_CONT_REL = 0.10           # sarake on "elossa" tällä osuudella keskiarvosta
_COHERENT = 0.15           # reunojen IQR saa olla tämä osuus korkeudesta
_DECK_SLAB = 150.0         # mm — kaista alareunan ympärillä
_DECK_REACH = 1200.0       # mm — kuinka kauas sivulle vaakatasoa seurataan
_DECK_SKIP = 100.0         # mm — pinta itse ei ole vaakataso
_DECK_BIN = 100.0
_DECK_BOTH = 0.50          # molemminpuolinen peitto tästä ylös = laatan reuna


def _profile(w: Wall, pts: np.ndarray):
    """Poikkileikkaus lattian ja katon VÄLISTÄ.

    Ei vyötärökaistaa: matala väliseinä korkeassa hallissa jää kokonaan sen
    ulkopuolelle. Laattamarginaali riittää rajaukseksi, koska pinnan
    yhtenäisyyden ratkaisee `_face_edges`, ei kaistan valinta.
    """
    a = np.array(w.axis[0], float)
    b = np.array(w.axis[1], float)
    L = float(np.linalg.norm(b - a))
    if L < _MIN_LEN or w.height < 1.0:
        return None
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    rel = pts[:, :2] - a
    t, perp, z = rel @ u, rel @ n, pts[:, 2]
    # Ikkuna on _DECK_REACH leveämpi kuin huippuhaku: laatan reunan testi
    # katsoo pinnan MOLEMMIN puolin, ja 1.5 m päässä oleva ehdokas jäisi
    # muuten ilman dataa toisella puolella (mitattu: käytettävää 15 mm).
    clear = ((t > 0.0) & (t < L) & (np.abs(perp) < _SEEK + _DECK_REACH)
             & (z > w.z_min + _SLAB_MARGIN)
             & (z < w.z_min + w.height - _SLAB_MARGIN))
    if clear.sum() < _MIN_JUDGE:
        return None
    return a, u, n, L, t[clear], perp[clear], z[clear]


def _gap_has_shelves(w: Wall, perp: np.ndarray, z: np.ndarray, p: float) -> bool:
    """Onko emäseinän ja ehdokaspinnan VÄLISSÄ hyllytasoja?

    Lattiasta kattoon ulottuva hyllykön etupinta on geometrisesti täysin sama
    kuvio kuin puolen metrin päässä seisova kipsiseinä — paitsi että hyllyssä
    ON HYLLYJÄ: väli täyttyy toistuvista vaakatasoista. Mitattu: synteettisen
    myymälän hyllyväli 6 tasoa (z = 500…5900, ~900 mm välein), Rohbaun aidon
    kipsiseinän väli 1 taso (palkkilinja z ≈ 5.1–5.5 m).
    """
    half = w.thickness / 2.0
    lo, hi = sorted([np.sign(p) * (half + _BAND), p - np.sign(p) * _BAND])
    zlo, zhi = w.z_min + 300.0, w.z_min + w.height - 300.0
    gap = (perp > lo) & (perp < hi) & (z > zlo) & (z < zhi)
    if gap.sum() < _MIN_JUDGE:
        return False
    nbins = max(10, int((zhi - zlo) / _SHELF_BIN))
    hist, edges = np.histogram(z[gap], bins=nbins, range=(zlo, zhi))
    peaks = np.flatnonzero(hist >= _SHELF_PEAK_REL * hist.mean())
    if len(peaks) == 0:
        return False
    levels = 1 + int((np.diff(edges[peaks]) > _SHELF_SEP).sum())
    return levels >= _SHELF_LEVELS


def _is_deck_edge(perp: np.ndarray, z: np.ndarray, p: float, z0: float) -> bool:
    """Onko "seinä" laatan reuna tai palkin kylki?

    Betonirungossa pystypinta on yhtä usein välipohjan reuna kuin seinä, ja
    laatan reuna on parempi seinä kuin aito seinä: tuki 0.80–0.82, jatkuvuus
    0.89–0.97 (aidoilla kipsiseinillä 0.40–0.82). Erottava todiste on
    ALAREUNASSA: laatan reunan alla vaakataso jatkuu pinnan MOLEMMIN PUOLIN,
    seinä katkaisee sen. Mitattu neljällä Rohbau-scenellä, 7 ehdokasta:
    molemminpuolinen peitto 0.92 kummallakin palkkilinjalla, **0.00 kaikilla
    viidellä aidolla seinällä** (GT Wall/Drywall).
    """
    base = np.abs(z - z0) < _DECK_SLAB
    if base.sum() < _MIN_JUDGE:
        return False
    nbins = max(1, int(_DECK_REACH / _DECK_BIN))
    worst = 1.0
    for sgn in (-1.0, 1.0):
        d = sgn * (perp[base] - p)
        sel = (d > _DECK_SKIP) & (d < _DECK_REACH)
        if sel.sum() < _MIN_JUDGE:
            return False
        bi = np.clip((d[sel] / _DECK_BIN).astype(np.int64), 0, nbins - 1)
        cnt = np.bincount(bi, minlength=nbins)
        worst = min(worst, float((cnt >= max(1.0, _CONT_REL * cnt.mean())).mean()))
    return worst >= _DECK_BOTH


def _face_edges(t: np.ndarray, zf: np.ndarray, L: float, ncol: int,
                min_h: float) -> tuple[float, float] | None:
    """Pinnan oma z-väli, ja onko se YKSI esine.

    Seinän pinta on yhtenäinen: jokainen sarake päättyy samaan ylä- ja
    alareunaan. Sohva + kaappi + komero peräkkäin muodostavat yhtä pitkän
    "pinnan", mutta niiden reunat heittelehtivät. Mitattu: Rohbaun aidon
    kipsiseinän yläreunan IQR 4–9 mm (0.00 × korkeus), asunnon huonekaluketjun
    1649 mm (0.61 × korkeus). Lattia ja katto ovat jo rajattu pois — muuten ne
    täyttävät joka sarakkeen ja reuna näyttää täydelliseltä kaikkialla.
    """
    if len(zf) < _MIN_JUDGE:
        return None
    ci = np.clip((t / L * ncol).astype(np.int64), 0, ncol - 1)
    counts = np.bincount(ci, minlength=ncol)
    live = np.flatnonzero(counts >= max(1.0, _CONT_REL * counts.mean()))
    if len(live) < 2:
        return None
    tops = np.array([np.percentile(zf[ci == k], 98.0) for k in live])
    bots = np.array([np.percentile(zf[ci == k], 2.0) for k in live])
    z0 = float(np.median(bots))
    h = float(np.median(tops)) - z0
    if h < min_h:
        return None
    iqr = max(float(np.subtract(*np.percentile(tops, (75, 25)))),
              float(np.subtract(*np.percentile(bots, (75, 25)))))
    if iqr > _COHERENT * h:
        return None
    return z0, h


def find_hidden_walls(walls: list[Wall], cloud) -> list[Wall]:
    """Lisäseinät niille rinnakkaispinnoille jotka jäivät ensimmäisen taakse."""
    from ordinate.core.qa.deviation import (
        _CONT_COL, _WAIST_HI, _WAIST_LO, _column_continuity,
    )

    pts = np.asarray(cloud.points, dtype=np.float64)
    if len(pts) == 0:
        return []

    found: list[Wall] = []
    for w in walls:
        prof = _profile(w, pts)
        if prof is None:
            continue
        a, u, n, L, t, perp, z = prof
        half = w.thickness / 2.0
        own = int((np.abs(np.abs(perp) - half) < _BAND).sum())
        if own < 1:
            continue

        nbins = max(1, int(2 * _SEEK / _BIN))
        hist, edges = np.histogram(perp, bins=nbins, range=(-_SEEK, _SEEK))
        centres = 0.5 * (edges[:-1] + edges[1:])
        ncol = max(1, int(L / _CONT_COL))

        taken: list[float] = []
        added = 0
        for j in np.argsort(-hist):
            if added >= _MAX_PER_WALL:
                break
            p = float(centres[j])
            if abs(abs(p) - half) < _MIN_GAP or any(abs(p - q) < 200.0 for q in taken):
                continue
            on = np.abs(perp - p) < _BAND
            if on.sum() < _MIN_MASS * own:
                break
            taken.append(p)
            if _gap_has_shelves(w, perp, z, p):
                continue

            edge = _face_edges(t[on], z[on], L, ncol,
                               max(_MIN_HEIGHT, _MIN_H_FRAC * w.height))
            if edge is None:
                continue
            z0, h = edge
            # Jatkuvuus mitataan pinnan OMASSA vyötärökaistassa.
            waist = on & (z > z0 + _WAIST_LO * h) & (z < z0 + _WAIST_HI * h)
            if waist.sum() < _MIN_JUDGE:
                continue
            ci = np.clip((t[waist] / L * ncol).astype(np.int64), 0, ncol - 1)
            if _column_continuity(np.bincount(ci, minlength=ncol)) < _MIN_CONT:
                continue
            if _is_deck_edge(perp, z, p, z0):
                continue

            # Näkyvä pinta on se joka on emäseinään päin — runko jää sen taakse.
            off = p + np.sign(p) * _NEW_THICK / 2.0
            p0 = a + off * n
            p1 = a + L * u + off * n
            added += 1
            found.append(Wall(
                id=f"wall_2nd_{len(found):03d}",
                confidence=0.5,
                classification="wall",
                source=ElementSource(method="second_face",
                                     notes=f"parallel-behind-{w.id}"),
                axis=[[round(float(p0[0]), 1), round(float(p0[1]), 1)],
                      [round(float(p1[0]), 1), round(float(p1[1]), 1)]],
                height=round(h, 1),
                thickness=_NEW_THICK,
                z_min=round(z0, 1),
            ))
    return found

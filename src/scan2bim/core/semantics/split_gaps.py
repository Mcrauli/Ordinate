"""Pilko seinä siitä kohtaa jossa sen alla ei ole mitään.

`overstretch.py` leikkaa seinän PÄÄT kun ne roikkuvat ilmassa, ja
`_trim_endpoints` kutistaa akselin evidenssiin. Kumpikaan ei koske seinän
KESKELLE, koska kattamaton keskiosa on yleensä oviaukko — ja oviaukon yli
seinän kuuluu jatkua.

Matalassa sokkeloisessa tilassa se oletus pettää. Mitattu koulun kellarilla
(198 seinää, 3274 m): mediaaniseinä on 15.7 m pitkä mutta sen pituudesta on
pystypinnan kattamaa vain 14 %, ja 78 % seinistä on katettu alle 30 %:sti.
Seinät jatkuvat toistensa ja huoneiden läpi, mikä näkyy mallissa ristikkona
ja mittarissa tarkkuutena 0.068.

Oviaukko on noin metrin, tässä katkotaan metrien aukoista: kattamaton jakso
pilkkoo seinän vasta kun se on `_MIN_GAP_MM` pitkä, eli selvästi leveintäkin
oviaukkoa pidempi. Aukkodetektori tarvitsee lyhyet aukot ehjän seinän alla,
joten niihin ei kosketa.
"""
from __future__ import annotations

import numpy as np

_MIN_GAP_MM = 1200.0     # mm — tätä pidempi kattamaton jakso katkaisee seinän.
                         # Standardi oviaukko on 900–1000 mm, joten kapeampaa
                         # ei pilkota. Mitattu sweepillä: Rohbau scene_07000 on
                         # BITILLEEN sama 2500, 1500 ja 1000 mm:llä (11 seinää,
                         # 189 m, kattavuus 0.946) eli oviaukot eivät pilkkoudu,
                         # kun taas kellari 333 → 489 seinää, 2464 → 2116 m ja
                         # tarkkuus 0.069 → 0.076. 700 mm veisi tarkkuutta vielä
                         # ylös mutta menisi oviaukon alle ja pudottaisi
                         # kattavuuden 0.299 → 0.286.
_COL_MM = 500.0          # mm — sarakkeen leveys katteen mittaukseen
_BAND_MM = 150.0         # mm — kaista seinäpinnan ympärillä
_MIN_PTS = 4             # pistettä sarakkeessa: alle tämän on tyhjä
_MIN_PIECE_MM = 900.0    # mm — tätä lyhyempi pala ei ole seinä


def split_walls_at_gaps(walls: list, pts: np.ndarray) -> list:
    """Katkaise seinät kohdista joissa pinta puuttuu metrien matkalta."""
    if pts is None or len(pts) == 0:
        return walls
    out: list = []
    for w in walls:
        pieces = _split_one(w, pts)
        out.extend(pieces if pieces else [w])
    return out


def _split_one(w, pts: np.ndarray) -> list:
    axis = getattr(w, "axis", None)
    if not axis or len(axis) < 2:
        return [w]
    a = np.asarray(axis[0], dtype=float)[:2]
    b = np.asarray(axis[-1], dtype=float)[:2]
    length = float(np.linalg.norm(b - a))
    if length < 2.0 * _MIN_PIECE_MM:
        return [w]

    u = (b - a) / length
    n = np.array([-u[1], u[0]])
    half = float(getattr(w, "thickness", 200.0)) / 2.0
    z_min = float(getattr(w, "z_min", pts[:, 2].min()))
    height = float(getattr(w, "height", 0.0))
    band = pts
    if height > 1.0:
        lo, hi = z_min + 0.25 * height, z_min + 0.75 * height
        band = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]
        if len(band) < 50:
            band = pts

    d = band[:, :2] - a
    s = d @ u
    t = d @ n
    on = (np.abs(np.abs(t) - half) < _BAND_MM) & (s > -_COL_MM) & (s < length + _COL_MM)
    if not on.any():
        return [w]

    n_col = max(int(length / _COL_MM), 1)
    idx = np.clip((s[on] / _COL_MM).astype(int), 0, n_col - 1)
    counts = np.bincount(idx, minlength=n_col)
    filled = counts >= _MIN_PTS
    if filled.all():
        return [w]

    # kattamattomat jaksot: pilko vain riittävän pitkistä
    pieces: list = []
    start = None
    # Jakson on oltava AIDOSTI kynnystä pidempi: pelkkä jakolasku pyöristää
    # 1200 mm:n kahdeksi 500 mm sarakkeeksi eli tuhanneksi millimetriksi, ja
    # silloin standardi oviaukko pilkkoutuisi.
    gap_cols = max(int(_MIN_GAP_MM / _COL_MM) + 1, 2)
    run = 0
    for i in range(n_col + 1):
        f = bool(filled[i]) if i < n_col else False
        if f:
            if run >= gap_cols and start is not None:
                pieces.append((start, i - run))
                start = None
            run = 0
            if start is None:
                start = i
        else:
            run += 1
    if start is not None:
        end = n_col - run if run >= gap_cols else n_col
        pieces.append((start, end))

    if len(pieces) < 2:
        return [w]

    out = []
    for k, (c0, c1) in enumerate(pieces):
        p0 = a + u * (c0 * _COL_MM)
        p1 = a + u * (min(c1 * _COL_MM, length))
        if float(np.linalg.norm(p1 - p0)) < _MIN_PIECE_MM:
            continue
        out.append(w.model_copy(update={
            "id": f"{w.id}_s{k}",
            "axis": [[round(float(p0[0]), 1), round(float(p0[1]), 1)],
                     [round(float(p1[0]), 1), round(float(p1[1]), 1)]],
        }))
    return out or [w]

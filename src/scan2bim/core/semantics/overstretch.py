"""Ylivenytyksen leikkaus: seinän pää joka on ILMASSA ja IRRALLAAN → evidenssiin.

`snap_corners` ja `close_open_corners` venyttävät akselin päitä risteyksiin, ja
niiden ainoa raja on GEOMETRINEN etäisyys (`_MAX_EXTEND` 1300 mm,
`_CLOSE_MAX_EXT` 2300 mm). Kumpikaan ei kysy onko venytetyllä osalla pisteitä,
joten seinä piirretään evidenssin yli. Mitattu asuntoskannauksella
(`data/_extent_qa.py`): wall_005 kate 0.63 (hännät 600 + 800 mm), wall_013 0.78
(800 mm), wall_010 0.70 (600 mm) — 3.8 m seinästä 1.4 m oli ilmassa.

Leikataan pää joka on kattamaton yli `_MIN_TAIL` mm:n matkalta JA jonka venytys
ei ole ansainnut paikkaansa. Jälkimmäinen on tosi kahdessa tapauksessa:

  a) pää on irrallaan (>`_OPEN_TOL` mm kaikista muista seinistä) — venytys ei
     osunut mihinkään, joten se ei ostanut mitään. Asunnossa wall_005:n ja
     wall_013:n venytetyt päät roikkuivat yhä 542 mm ja 495 mm irti.
  b) pää osuu seinään, mutta SE seinä on liitoskohdassa itsekin kattamaton —
     nurkka lepää tyhjän päällä eli se on keksitty. Asunnossa wall_002 ja
     wall_010 kohtasivat juuri näin (hännät 400 ja 600 mm, kumpikaan pää ei
     katettu).

Nurkkaan jossa vastinseinällä ON pintaa ei kosketa: silloin venytys sulkee
aidon nurkan ja on laillinen mallinnusvara. Asunnon wall_005:n 800 mm häntä on
juuri tällainen (`wall_ext_002` on katettu liitoskohdassa) eikä se leikkaudu.

Kattamaton KESKIOSA on laillinen (oviaukko/ikkuna) eikä sitä katsota lainkaan —
vain päät.

"""
from __future__ import annotations

import numpy as np

_TOL = 60.0           # mm — pinnan kaista akselin normaalin suunnassa
_BIN = 200.0          # mm — katteen resoluutio akselin suunnassa
_MIN_PTS = 8          # pisteitä binissä = "onko siellä yhtään mitään"
_MIN_TAIL = 700.0     # mm — tätä lyhyempi häntä on mallinnusvaraa, ei virhe
_OPEN_TOL = 60.0      # mm — pää on irrallaan (sama kuin corner_snap._OPEN_TOL)
_MIN_KEEP = 800.0     # mm — leikkaus ei saa jättää seinää tätä lyhyemmäksi
_Z_FLOOR = 400.0      # mm — lattian roina pois
_Z_CEIL = 300.0       # mm — katon roina pois


def _band(model, walls) -> tuple[float, float]:
    """Vyöhyke jolta kate luetaan: lattian ja katon välistä, reunat pois."""
    floors = [s.elevation for s in model.slabs if s.slab_type == "floor"]
    ceils = [s.elevation for s in model.slabs if s.slab_type in ("ceiling", "roof")]
    zf = min(floors) if floors else min((w.z_min for w in walls), default=0.0)
    zc = max(ceils) if ceils else max((w.z_min + w.height for w in walls), default=zf + 2700.0)
    return zf + _Z_FLOOR, zc - _Z_CEIL


def _coverage(w, xy: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    a = np.asarray(w.axis[0], float)
    b = np.asarray(w.axis[1], float)
    d = b - a
    L = float(np.linalg.norm(d))
    if L < 1.0:
        return np.zeros(0, bool), L, a, b
    u = d / L
    n = np.array([-u[1], u[0]])
    rel = xy - a
    s = rel @ u
    t = rel @ n
    half = w.thickness / 2.0
    sel = (np.abs(t - half) < _TOL) | (np.abs(t + half) < _TOL)
    nb = max(int(L / _BIN), 1)
    hist, _ = np.histogram(s[sel], bins=nb, range=(0.0, L))
    return hist >= _MIN_PTS, L, a, b


def _pt_seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    d = b - a
    L2 = float(d @ d)
    if L2 <= 0.0:
        return float(np.linalg.norm(p - a))
    q = max(0.0, min(1.0, float((p - a) @ d) / L2))
    return float(np.linalg.norm(p - (a + q * d)))


def trim_overstretched_walls(model, cloud) -> list[tuple[str, float]]:
    """Leikkaa kattamattomat, irralliset päät. Palauttaa [(id, leikattu_mm)]."""
    if cloud is None or not model.walls:
        return []
    pts = np.asarray(cloud.points)
    if pts.size == 0:
        return []
    zlo, zhi = _band(model, model.walls)
    xy = pts[(pts[:, 2] > zlo) & (pts[:, 2] < zhi)][:, :2]
    if len(xy) == 0:
        return []

    # Kate luetaan KAIKILTA seiniltä kertaalleen alkuperäisestä geometriasta:
    # nurkan pätevyys on kysymys vastinseinän katteesta, ja jos sitä luettaisiin
    # jo leikatusta akselista, ensimmäinen leikkaus muuttaisi seuraavan tuomion.
    prof = [_coverage(w, xy) for w in model.walls]
    n_w = len(model.walls)
    trimmed: list[tuple[str, float]] = []

    def junction_is_earned(i: int, p: np.ndarray) -> bool:
        """Osuuko pää seinään jolla on pintaa juuri liitoskohdassa."""
        earned = False
        for j in range(n_w):
            if j == i:
                continue
            cov_j, L_j, a_j, b_j = prof[j]
            if L_j < 1.0 or _pt_seg_dist(p, a_j, b_j) > _OPEN_TOL:
                continue
            if not len(cov_j):
                continue
            u_j = (b_j - a_j) / L_j
            k = int(np.clip(float((p - a_j) @ u_j) / _BIN, 0, len(cov_j) - 1))
            if cov_j[max(0, k - 1):k + 2].any():
                earned = True
        return earned

    for i, w in enumerate(model.walls):
        cov, L, a, b = prof[i]
        if not cov.any() or L < _MIN_KEEP:
            continue
        nb = len(cov)
        first = int(np.argmax(cov))
        last = nb - 1 - int(np.argmax(cov[::-1]))
        cut_a = first * _BIN
        cut_b = (nb - 1 - last) * _BIN
        u = (b - a) / L

        take_a = cut_a > _MIN_TAIL and not junction_is_earned(i, a)
        take_b = cut_b > _MIN_TAIL and not junction_is_earned(i, b)
        if not (take_a or take_b):
            continue
        da = cut_a if take_a else 0.0
        db = cut_b if take_b else 0.0
        if L - da - db < _MIN_KEEP:
            continue

        w.axis = [list(a + u * da), list(b - u * db)]
        trimmed.append((w.id, da + db))

        if da or db:
            new_len = L - da - db
            keep = []
            for o in model.openings:
                if o.wall_id != w.id:
                    keep.append(o)
                    continue
                pos = o.position_along - da
                if 0.0 <= pos <= new_len:
                    o.position_along = pos
                    keep.append(o)
            model.openings = keep

    return trimmed

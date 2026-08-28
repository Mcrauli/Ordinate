"""Poista seinä jonka pinnalla suodatin ei näe seinää.

`prune_unsupported_walls` mittaa onko seinän kohdalla PINTAA. Se ei kysy mitä
se pinta on, koska geometria ei voi tietää: 200 mm putki ja 200 mm seinä ovat
molemmat pystysuoria tasoja samassa paikassa.

Semanttinen suodatin osaa erottaa ne — se luokittelee jokaisen voxelin
(seinä / lattia / katto / palkki / pilari / kaluste) — mutta putki heittää
tiedon pois ja antaa detektorille vain keep/remove. AGENTS.md kirjaa saman:
"malli erottaa seinän ja palkin toisistaan; `filter` heittää sen tiedon pois".

Mitattu koulun kellarilla (430 seinää, 36 asemaa): mallin seinäkaistassa
olevien pisteiden luokista on seinää mediaanina 0.35, ja **124 seinää 304:stä
jää alle 0.30:n**. Pahimmilla osuus on 0.00 — kaistassa on 85–318 clutter-
pistettä eikä yhtään seinäpistettä. Ne ovat putkia ja kanavia.

Sääntö ei voi toimia ilman labeleita, joten se on no-op kun suodatin ei ole
ajanut. Se on tarkoitus: geometrinen karsinta hoitaa oman osuutensa erikseen.
"""
from __future__ import annotations

import numpy as np

_WALLISH = (2, 5, 6)      # S3DIS: wall, window, door — seinätasoon kuuluvat
_MIN_FRAC = 0.30          # tätä pienempi seinäosuus = pinta ei ole seinä
_MIN_PTS = 50             # alle tämän ei voi päätellä mitään
_BAND_MM = 150.0          # mm — kaista seinäpinnan ympärillä
_WAIST_LO, _WAIST_HI = 0.30, 0.70    # osuus korkeudesta: vyötärökaista
_MIN_LEN = 2000.0         # mm — lyhyt seinä ei kerää tarpeeksi näyttöä


def prune_non_wall_surfaces(model, cloud, labels) -> list[str]:
    """Poista seinät joiden pinta on suodattimen mukaan muuta kuin seinää.

    Palauttaa poistettujen id:t. Ei tee mitään ilman labeleita.
    """
    if labels is None or not model.walls:
        return []
    pts = np.asarray(cloud.points)
    if len(pts) < 1000:
        return []

    z_min = min((w.z_min for w in model.walls), default=float(pts[:, 2].min()))
    height = max((w.height for w in model.walls), default=0.0)
    if height <= 0.0:
        return []
    lo = z_min + _WAIST_LO * height
    hi = z_min + _WAIST_HI * height
    band = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]
    if len(band) < 1000:
        return []

    pred = labels.lookup(band)
    xy = band[:, :2]
    drop: list[str] = []
    for w in model.walls:
        if len(w.axis) < 2:
            continue
        a = np.asarray(w.axis[0], dtype=float)[:2]
        b = np.asarray(w.axis[-1], dtype=float)[:2]
        length = float(np.linalg.norm(b - a))
        if length < _MIN_LEN:
            continue
        u = (b - a) / length
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        sel = ((s > 0) & (s < length)
               & (np.abs(np.abs(t) - w.thickness / 2.0) < _BAND_MM))
        n_sel = int(sel.sum())
        if n_sel < _MIN_PTS:
            continue          # ei näyttöä → jätä geometriselle karsinnalle
        seen = pred[sel]
        known = seen >= 0
        if int(known.sum()) < _MIN_PTS:
            continue
        frac = float(np.isin(seen[known], _WALLISH).mean())
        if frac < _MIN_FRAC:
            drop.append(w.id)

    if drop:
        keep = set(drop)
        model.walls = [w for w in model.walls if w.id not in keep]
    return drop

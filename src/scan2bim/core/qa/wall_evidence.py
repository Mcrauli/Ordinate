"""Seinäkohtaiset todisteet pilvestä per-projekti-oppimista varten.

Globaali kynnys on kaatunut tässä projektissa kerta toisensa jälkeen, koska
piirteiden TASO riippuu rakennuksesta ja keilauksesta. Saman rakennuksen
sisällä ne erottelevat: koulun kellarissa käyttäjän 208 labelilla yhdistelmä
antoi AUC 0.912 kun paras yksittäinen piirre 0.776 (`data/_perproj_probe.py`).

Tämä mittaa ne piirteet joka ajosta ja kirjoittaa ne `Wall.evidence`en, jotta
GUI voi oppia käyttäjän korjauksista ilman pistepilveä (putki ajaa erillisessä
prosessissa). Määritelmät ovat TÄSMÄLLEEN samat kuin koettimessa — muuten
mitattu tulos ei siirtyisi tuotteeseen.

Arvoja EI saa verrata rakennusten välillä: `logpts` riippuu tiheydestä ja
`contrast` ympäristöstä. Ne ovat saman mallin sisäistä vertailua varten.
"""
from __future__ import annotations

import numpy as np

from scan2bim.core.geometry.xy_index import index_for
from scan2bim.schemas.model import StructuralModel

_WAIST = (0.30, 0.70)
_REACH = 1300.0


def _evidence(w, pts: np.ndarray, index, med_len: float) -> dict[str, float] | None:
    a = np.asarray(w.axis[0], float)[:2]
    b = np.asarray(w.axis[-1], float)[:2]
    L = float(np.linalg.norm(b - a))
    if L < 300.0:
        return None
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    th = float(w.thickness or 200.0)
    half = th / 2.0
    idx = index.near_segment(a, u, n, half + _REACH, 0.0, L)
    if not len(idx):
        return None
    P = pts[idx]
    z0 = float(w.z_min or 0.0)
    h = float(w.height or 0.0)
    zlo, zhi = z0 + _WAIST[0] * h, z0 + _WAIST[1] * h
    d = P[:, :2] - a
    t, perp, z = d @ u, d @ n, P[:, 2]
    inb = (t > 0) & (t < L) & (z > zlo) & (z < zhi)
    face = inb & (np.abs(np.abs(perp) - half) < 60.0)
    if int(face.sum()) < 60:
        return None

    pf = perp[face]
    sign = 1.0 if np.median(pf) > 0 else -1.0
    dom = pf[np.sign(pf) == sign]
    flat = float(np.median(np.abs(dom - np.median(dom)))) if len(dom) > 20 else 99.0

    side = inb & (np.abs(perp) > half + 750.0) & (np.abs(perp) < half + 1250.0)
    on, off = int(face.sum()), int(side.sum())
    contrast = (on / max(off, 1)) if off else float(on)

    zf = z[face]
    hspan = float(np.percentile(zf, 98) - np.percentile(zf, 2)) / max(h, 1.0)
    htop = float(np.percentile(zf, 98) - z0) / max(h, 1.0)

    behind = inb & (sign * perp < -(half + 150.0)) & (sign * perp > -(half + _REACH))
    front = inb & (sign * perp > half + 150.0) & (sign * perp < half + _REACH)
    body = int(behind.sum()) / max(int(behind.sum()) + int(front.sum()), 1)

    cols = np.clip(((t[face] / L) * 16).astype(int), 0, 15)
    tops = np.array([np.percentile(zf[cols == i], 95) if (cols == i).sum() > 15
                     else np.nan for i in range(16)])
    topvar = float(np.nanstd(tops)) / max(h, 1.0) if np.isfinite(tops).sum() > 3 else 0.0
    cover = float(np.unique(cols).size / 16.0)

    return {
        "len": round(L / max(med_len, 1.0), 4),
        "logpts": round(float(np.log10(max(on, 1))), 4),
        "thick": round(th / 200.0, 4),
        "flat": round(min(flat, 60.0) / 20.0, 4),
        "contrast": round(min(contrast, 20.0), 4),
        "hspan": round(hspan, 4),
        "htop": round(htop, 4),
        "body": round(body, 4),
        "topvar": round(min(topvar, 1.0), 4),
        "cover": round(cover, 4),
    }


def measure_wall_evidence(model: StructuralModel, cloud) -> int:
    """Kirjoita `Wall.evidence` jokaiselle mitattavissa olevalle seinälle.

    Palauttaa mitattujen seinien määrän. Liian vähän pintaa → `None`
    (ei mitattu), ei nollia: nolla olisi väite.
    """
    pts = np.asarray(cloud.points)
    if not len(pts) or not model.walls:
        return 0
    index = index_for(cloud, pts)
    lens = [float(np.linalg.norm(np.asarray(w.axis[-1], float)[:2]
                                 - np.asarray(w.axis[0], float)[:2])) for w in model.walls]
    med_len = float(np.median(lens)) if lens else 1.0
    n = 0
    for w in model.walls:
        w.evidence = _evidence(w, pts, index, med_len)
        n += w.evidence is not None
    return n

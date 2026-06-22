"""Huonetunnistus (IfcSpace) seinien keskilinjoista.

Seinät muodostavat tasograafin; sen rajaamat suljetut alueet ovat huoneita.
Käytetään shapelyn ``polygonize``:a, joka solmittaa viivat risteyksissä ja
palauttaa kaikki suljetut monikulmiot. Jokainen riittävän kokoinen monikulmio
= yksi huone.

Sisään: list[Wall] + floor/ceiling Z → ulos: list[Space].
"""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import ElementSource, Space

_EXTEND = 120.0        # mm — jatka seinänpäitä jotta nurkat solmittuvat varmasti
_MIN_AREA = 1_300_000.0   # mm² (~1.3 m²) — pienin huone (komero/wc)
_MAX_AREA = 90_000_000.0  # mm² (~90 m²) — tätä suurempi = koko asunnon ulkokehä, ohitetaan


def detect_rooms(walls: list, floor_z: float, ceiling_z: float) -> list[Space]:
    if len(walls) < 3:
        return []
    try:
        from shapely.geometry import LineString
        from shapely.ops import polygonize, unary_union
    except ImportError:
        return []

    lines = []
    for w in walls:
        if len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], dtype=float)
        p1 = np.array(w.axis[1], dtype=float)
        d = p1 - p0
        ln = float(np.linalg.norm(d))
        if ln < 1.0:
            continue
        u = d / ln
        p0e = p0 - _EXTEND * u
        p1e = p1 + _EXTEND * u
        lines.append(LineString([(p0e[0], p0e[1]), (p1e[0], p1e[1])]))

    if len(lines) < 3:
        return []

    noded = unary_union(lines)          # solmita risteyksissä
    polys = list(polygonize(noded))
    if not polys:
        return []

    spaces: list[Space] = []
    for poly in polys:
        area = float(poly.area)
        if area < _MIN_AREA or area > _MAX_AREA:
            continue
        simplified = poly.simplify(40.0, preserve_topology=True)
        coords = list(simplified.exterior.coords)[:-1]   # pudota sulkeva duplikaatti
        if len(coords) < 3:
            continue
        boundary = [[round(float(x), 1), round(float(y), 1)] for x, y in coords]
        spaces.append(Space(
            id=f"space_{len(spaces):03d}",
            confidence=round(min(1.0, area / 20_000_000.0), 3),
            source=ElementSource(method="polygonize"),
            boundary=boundary,
            floor_z=round(float(floor_z), 1),
            ceiling_z=round(float(ceiling_z), 1),
        ))
    return spaces

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
_MIN_AREA = 1_800_000.0   # mm² (~1.8 m²) — pienin huone (komero/wc); alle = perimetrin
                          # ja sisäseinän väliin jäävä kuollut kaista (valehuone), ei tila
# Ulkokehä-kasvo (koko rakennuksen ääriviiva) hylätään sillä että se SISÄLTÄÄ toisen
# kasvon, ei absoluuttisella pinta-alalla. Absoluuttinen 90 m² -katto oli asuntokoosta
# johdettu ja teki ison tilan tunnistuksen mahdottomaksi: mitattu synteettisellä
# 72×48 m myymälällä 3456 m² myyntialue putosi katosta → 0 tilaa siellä missä
# arkkitehti tarvitsee niitä eniten. polygonize antaa minimikasvot, joten sisäkkäisyys
# esiintyy vain kun kehän sisällä on erillinen (kytkemätön) rengas = juuri ulkokehä.
# Sliver-suodatus: kahden lähes yhdensuuntaisen seinän väliin (ohut rako) syntyy
# usein pitkä ja kapea valehuone, jonka pinta-ala silti ylittää _MIN_AREA. Hylätään
# liian kapeat tai liian pitkänomaiset polygonit ennen kuin ne muuttuvat huoneiksi.
_MIN_WIDTH = 700.0     # mm — minimi-rotated-rectangle kapein sivu alle tämän = sliver
_MAX_ASPECT = 8.0      # pitkä/kapea-suhde yli tämän = käytäväsliver,
_ASPECT_AREA = 6_000_000.0  # mm² (~6 m²) — paitsi jos pinta-ala riittää aitoon käytävään


_SNAP_PERP = 400.0     # mm — kontuurireuna kohdistetaan tätä lähempänä olevaan seinään
_SNAP_COS = 0.9962     # 5° — reunan ja seinän suuntaero
_SNAP_COVER = 0.5      # osuus reunasta jonka seinän on katettava


def _snap_ring_to_walls(ring, walls) -> list[tuple[float, float]]:
    """Siirrä lattiakontuurin reunat niiden seinien keskilinjoille jotka niitä vastaavat.

    Kontuuri kulkee seinän ULKOpinnan tasalla (mitattu myymälällä 260 mm
    keskilinjojen ulkopuolella), joten sellaisenaan lisättynä seinäviivat jäävät
    kellumaan renkaan sisään: ne eivät solmitu siihen, iso kasvo saa reiät ja
    putoaa ulkokehänä — juuri se tila jota haettiin. Kohdistuksen jälkeen reuna
    JA seinä ovat samaa viivaa, jolloin tilan raja on seinän keskilinjassa
    (sama konventio kuin muualla) ja graafi solmittuu. Reuna jolle ei löydy
    seinää jää paikalleen — se on nimenomaan se kohta jota suljetaan."""
    pts = [(float(x), float(y)) for x, y in ring]
    n = len(pts)
    if n < 3 or not walls:
        return pts

    axes = []
    for w in walls:
        if len(w.axis) < 2:
            continue
        a = np.array(w.axis[0], float)
        b = np.array(w.axis[1], float)
        L = float(np.linalg.norm(b - a))
        if L >= 1.0:
            axes.append((a, (b - a) / L, L))

    # reuna i = pts[i] -> pts[i+1]; talletetaan (piste linjalla, suunta)
    edges = []
    for i in range(n):
        p, q = np.array(pts[i]), np.array(pts[(i + 1) % n])
        d = q - p
        L = float(np.linalg.norm(d))
        if L < 1.0:
            edges.append((p, np.array([1.0, 0.0])))
            continue
        u = d / L
        best = None
        for a, v, wl in axes:
            if abs(float(u @ v)) < _SNAP_COS:
                continue
            nv = np.array([-v[1], v[0]])
            if abs(float((p - a) @ nv)) > _SNAP_PERP:
                continue
            s = np.array([(p - a) @ v, (q - a) @ v])
            cover = max(0.0, min(wl, s.max()) - max(0.0, s.min())) / L
            if cover < _SNAP_COVER:
                continue
            dist = abs(float((p - a) @ nv)) + abs(float((q - a) @ nv))
            if best is None or dist < best[0]:
                best = (dist, a, v)
        edges.append((best[1], best[2]) if best else (p, u))

    out = []
    for i in range(n):
        p0, u0 = edges[i - 1]
        p1, u1 = edges[i]
        den = u0[0] * (-u1[1]) - u0[1] * (-u1[0])
        if abs(den) < 1e-9:
            out.append(pts[i])
            continue
        rhs = p1 - p0
        t = (rhs[0] * (-u1[1]) - rhs[1] * (-u1[0])) / den
        x = p0 + t * u0
        out.append((float(x[0]), float(x[1])))
    return out


_COVERED_FRAC = 0.10   # kontuurikasvo hylätään jos tämän verran on jo tilaa
# Kontuurin varassa oleva tila on määritelmän mukaan sellainen jota MIKÄÄN seinä ei
# sulje → sitä ei ole voitu varmistaa seinäevidenssillä, ja kontuurin oma
# sijaintiprior on heikko. Riman on siksi oltava korkeampi kuin seinien rajaamalla
# tilalla. Mitattu apt2:lla: ilman tätä syntyi 0.86 × 2.54 m "huone" (1.82 m²)
# väärin sijoittuneen perimetriseinän (t=329, conf 0.25) ja aidon seinän väliin.
# Aito pieni huone on seinien ympäröimä eikä tarvitse kontuuria.
_CONTOUR_MIN_AREA = 6_000_000.0   # mm² (~6 m²)
_CONTOUR_MIN_WIDTH = 1200.0       # mm


def _min_rect(poly) -> tuple[float, float]:
    """Minimi-suorakaiteen (kapein, pisin) sivu mm; (0, 0) jos ei laskettavissa."""
    try:
        rc = list(poly.minimum_rotated_rectangle.exterior.coords)
    except Exception:
        return 0.0, 0.0
    e1 = np.hypot(rc[1][0] - rc[0][0], rc[1][1] - rc[0][1])
    e2 = np.hypot(rc[2][0] - rc[1][0], rc[2][1] - rc[1][1])
    return float(min(e1, e2)), float(max(e1, e2))


def _accept_faces(polys) -> list:
    """Polygonize-kasvot → hyväksytyt huonepolygonit (koko, ulkokehä, sliver)."""
    out = []
    for poly in polys:
        area = float(poly.area)
        if area < _MIN_AREA:
            continue
        # Ulkokehä-kasvo: polygonize palauttaa sen REIÄLLISENÄ (erilliset
        # sisärenkaat = huoneet). Reikä on siis suora tunniste — eikä
        # `.exterior`-rajaus saisi koskaan kirjata sitä tilaksi, koska boundary
        # jättäisi reiät huomiotta ja ala laskettaisiin kahteen kertaan
        # (mitattu: 80 m² kirjattu kun kasvon oikea ala on 71 m²).
        if len(poly.interiors) > 0:
            continue
        # Sliver-hylkäys: mittaa minimi-suorakaiteen sivut (pituus × leveys).
        width, length = _min_rect(poly)
        if width:
            aspect = length / width if width > 1.0 else 1e9
            if width < _MIN_WIDTH:
                continue
            if aspect > _MAX_ASPECT and area < _ASPECT_AREA:
                continue
        out.append(poly)
    return out


def detect_rooms(walls: list, floor_z: float, ceiling_z: float,
                 boundaries: list | None = None) -> list[Space]:
    """``boundaries``: lattiakontuurit (`detect_floor_contours`) suljettuina renkaina.

    Seinärengas ei sulkeudu isossa tilassa: mitattu 72×48 m myymälällä polygonize
    antaa seinistä vain 3 kasvoa ja 150×100 m:llä **0 tilaa** — myyntialuetta ei
    ole olemassa kasvona jota suodattaa, koska perimetri pirstoutuu (itäseinä 5
    palana, suurin rako 5.3 m). Lattiakontuuri on rakenteeltaan suljettu, joten
    se antaa kasvon sinne missä seinä puuttuu.

    Kontuuri saa VAIN TÄYDENTÄÄ, ei leikata. Sen sijaintiprior on heikko
    (25 mm ruudukko + dilaatio → kymmenien mm bias), joten seinien rajaamiin
    tiloihin sitä ei päästetä: tilat lasketaan ensin pelkistä seinistä, ja
    kontuurin tuomista kasvoista otetaan vain ne jotka eivät ole jo katettuja.
    Ilman tätä rajausta asunnon huoneala putosi 55.73 → 53.62 m² (−3.8 %) —
    mitattu regressio, ei arvio."""
    if len(walls) < 3:
        return []
    try:
        from shapely.geometry import LineString
        from shapely.ops import polygonize, unary_union
    except ImportError:
        return []

    wall_lines = []
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
        wall_lines.append(LineString([(p0e[0], p0e[1]), (p1e[0], p1e[1])]))

    if len(wall_lines) < 3:
        return []

    kept = _accept_faces(polygonize(unary_union(wall_lines)))

    ring_lines = []
    for ring in boundaries or []:
        pts = _snap_ring_to_walls(ring, walls)
        if len(pts) >= 3:
            ring_lines.append(LineString([*pts, pts[0]]))
    if ring_lines:
        covered = unary_union(kept) if kept else None
        for poly in _accept_faces(polygonize(unary_union(wall_lines + ring_lines))):
            if covered is not None:
                inter = poly.intersection(covered).area
                if inter > _COVERED_FRAC * poly.area:
                    continue
            if poly.area < _CONTOUR_MIN_AREA or _min_rect(poly)[0] < _CONTOUR_MIN_WIDTH:
                continue
            kept.append(poly)

    spaces: list[Space] = []
    for poly in kept:
        area = float(poly.area)
        area = float(poly.area)
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

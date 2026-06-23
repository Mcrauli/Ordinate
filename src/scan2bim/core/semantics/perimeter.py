"""Ulkoseinät lattian ulkorajasta (Cloud2BIM-idea).

Detektori löytää sisäseinät hyvin, mutta perimetri jää usein vajaaksi
(keilausvarjot ulkoseinien kohdalla, ikkunat, kalusteet). Lattian
pistekontuuri sen sijaan on luotettava — joka reuna, jolla ei jo ole
seinää, saa ulkoseinän. Näin perimetri sulkeutuu aina ja huoneet
muodostuvat reunoille asti.

Sisään: lattiakontuuri + olemassa olevat seinät → ulos: lisäseinät.
"""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import ElementSource, Wall

_MIN_EDGE = 1000.0         # mm — lyhyempiä reunoja ei muuteta seiniksi
_EXT_THICKNESS = 300.0     # mm — ulkoseinän oletuspaksuus
_COVER_PERP = 700.0        # mm — olemassa oleva seinä "kattaa" reunan jos näin lähellä
_COVER_COS = 0.94          # suuntien yhdensuuntaisuus (~20°)
_COVER_OVERLAP = 0.35      # vaadittu pituuspeitto jotta reuna katsotaan katetuksi
_SIMPLIFY_TOL = 400.0      # mm — kontuurin yksinkertaistus (rosoiset reunat pois)


def add_perimeter_walls(
    boundary: list[list[float]],
    existing: list[Wall],
    z_min: float,
    height: float,
) -> list[Wall]:
    """Palauttaa lisäseinät lattiakontuurin kattamattomille reunoille."""
    if not boundary or len(boundary) < 3:
        return []

    boundary = _simplify_boundary(boundary)
    if len(boundary) < 3:
        return []

    pts = [np.array(p, dtype=float) for p in boundary]
    n = len(pts)
    # Polygonin kiertosuunta (signed area): määrää johdonmukaisen ULOSPÄIN-normaalin
    # myös koveralle (L-muotoiselle) kontuurille — sentroidi epäonnistuu siinä.
    area2 = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    ccw = area2 > 0.0
    new_walls: list[Wall] = []
    idx = 0
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        seg = b - a
        seg_len = float(np.linalg.norm(seg))
        if seg_len < _MIN_EDGE:
            continue
        if _edge_covered(a, b, seg / seg_len, seg_len, existing):
            continue
        # Lattiakontuuri = ulkoseinän SISÄPINTA (skannauksen reuna). Siirrä akseli
        # ULOSPÄIN puoli paksuutta, jotta mallin sisäpinta osuu kontuuriin (bias→0)
        # — ei symmetristä keskitystä joka työntäisi sisäpinnan thickness/2 ohi.
        u = seg / seg_len
        # CCW-polygonissa ulkonormaali on (uy,-ux); CW:ssä (-uy,ux).
        nrm = np.array([u[1], -u[0]]) if ccw else np.array([-u[1], u[0]])
        off = nrm * (_EXT_THICKNESS / 2.0)
        a2 = a + off
        b2 = b + off
        new_walls.append(Wall(
            id=f"wall_ext_{idx:03d}",
            confidence=0.5,
            classification="wall",
            source=ElementSource(method="floorplan", notes="perimeter-from-slab"),
            axis=[[round(float(a2[0]), 1), round(float(a2[1]), 1)],
                  [round(float(b2[0]), 1), round(float(b2[1]), 1)]],
            height=round(float(height), 1),
            thickness=_EXT_THICKNESS,
            z_min=round(float(z_min), 1),
        ))
        idx += 1
    return new_walls


_GRID_SNAP = 500.0   # mm — kärjet snäpätään tähän ruudukkoon suoristusta varten


def _simplify_boundary(boundary: list[list[float]]) -> list[list[float]]:
    """Suorista rosoinen lattiakontuuri rectilineaariseksi monikulmioksi.

    1) simplify (poista pikkupätkät), 2) kierrä hallitsevaan suuntaan,
    3) snäppää kärjet ruudukkoon (akselinmukaiset reunat), 4) kierrä takaisin.
    """
    try:
        from shapely.geometry import Polygon
    except ImportError:
        return boundary
    poly = Polygon(boundary)
    if not poly.is_valid:
        poly = poly.buffer(0)
    poly = poly.simplify(_SIMPLIFY_TOL, preserve_topology=True)
    if poly.is_empty or poly.geom_type != "Polygon":
        return boundary
    pts = np.array(poly.exterior.coords[:-1], dtype=float)
    if len(pts) < 4:
        return [[float(x), float(y)] for x, y in pts]

    theta = _boundary_angle(pts)
    c, s = np.cos(-theta), np.sin(-theta)
    R = np.array([[c, -s], [s, c]])
    rot = pts @ R.T

    rot[:, 0] = _snap_axis(rot[:, 0])
    rot[:, 1] = _snap_axis(rot[:, 1])

    back = rot @ R  # R⁻¹ = Rᵀ → (R·x) takaisin
    out = _dedup_consecutive(back)
    return [[round(float(x), 1), round(float(y), 1)] for x, y in out]


def _boundary_angle(pts: np.ndarray) -> float:
    """Hallitseva reunakulma [0,π/2), pituuspainotettu (jakso π/2 → ×4)."""
    sin_sum = cos_sum = 0.0
    n = len(pts)
    for i in range(n):
        d = pts[(i + 1) % n] - pts[i]
        ln = float(np.hypot(d[0], d[1]))
        if ln < 1.0:
            continue
        a = np.arctan2(d[1], d[0])
        sin_sum += ln * np.sin(4 * a)
        cos_sum += ln * np.cos(4 * a)
    return float(np.arctan2(sin_sum, cos_sum) / 4.0) if (sin_sum or cos_sum) else 0.0


def _snap_axis(vals: np.ndarray) -> np.ndarray:
    """Snäppää arvot klustereihin (välin _GRID_SNAP sisällä = sama linja)."""
    order = np.argsort(vals)
    out = vals.copy()
    cluster = [order[0]]
    for k in order[1:]:
        if vals[k] - vals[cluster[-1]] <= _GRID_SNAP:
            cluster.append(k)
        else:
            out[cluster] = np.mean(vals[cluster])
            cluster = [k]
    out[cluster] = np.mean(vals[cluster])
    return out


def _insert_corners(pts: np.ndarray, tol: float = 50.0) -> np.ndarray:
    """Lisää L-nurkka jokaiselle vinolle reunalle → vain vaaka/pystyreunat (kierretyssä kehyksessä)."""
    out = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        out.append(a)
        if abs(b[0] - a[0]) > tol and abs(b[1] - a[1]) > tol:
            out.append(np.array([b[0], a[1]]))  # vaaka sitten pysty
    return np.array(out)


def _dedup_consecutive(pts: np.ndarray) -> np.ndarray:
    keep = []
    n = len(pts)
    for i in range(n):
        if not keep or np.hypot(*(pts[i] - keep[-1])) > 1.0:
            keep.append(pts[i])
    # poista kollineaariset
    res = []
    m = len(keep)
    for i in range(m):
        a, b, c = keep[(i - 1) % m], keep[i], keep[(i + 1) % m]
        d1, d2 = b - a, c - b
        l1, l2 = np.hypot(*d1), np.hypot(*d2)
        if l1 < 1 or l2 < 1 or abs(float(np.dot(d1 / l1, d2 / l2))) < 0.999:
            res.append(b)
    return np.array(res) if len(res) >= 3 else np.array(keep)


def _edge_covered(a, b, u, seg_len, existing):
    """True jos jokin olemassa oleva seinä on tämän reunan suuntainen, lähellä ja peittää sen."""
    n_vec = np.array([-u[1], u[0]])
    for w in existing:
        if len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], dtype=float)
        p1 = np.array(w.axis[1], dtype=float)
        d = p1 - p0
        wl = float(np.linalg.norm(d))
        if wl < 1.0:
            continue
        wu = d / wl
        if abs(float(np.dot(wu, u))) < _COVER_COS:
            continue
        # kohtisuora etäisyys reunalta seinään
        perp = abs(float(np.dot(p0 - a, n_vec)))
        if perp > _COVER_PERP:
            continue
        # pituuspeitto reunan suunnassa
        t0 = float(np.dot(p0 - a, u))
        t1 = float(np.dot(p1 - a, u))
        lo, hi = min(t0, t1), max(t0, t1)
        overlap = min(hi, seg_len) - max(lo, 0.0)
        if overlap >= _COVER_OVERLAP * seg_len:
            return True
    return False

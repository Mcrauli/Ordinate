"""Huonepolygoni seinien päätepisteiden perusteella.

Lähde: corner_snap on jo siirtänyt seinien päätepisteet leikkauspisteisiin.
Tässä klusteroidaan lähekkäiset pisteet ja järjestetään CCW-polygoni.
Laskennallisia leikkauspisteitä lisätään vain jos MOLEMMAT seinät loppuvat lähelle.
"""
from __future__ import annotations

import numpy as np
from ordinate.schemas.model import Wall

_CORNER_SNAP_TOL = 250.0   # mm — lähempänä olevat päätepisteet = sama nurkka
_BOTH_ENDS_DIST  = 600.0   # mm — leikkauspiste lisätään vain jos molemmat päät tässä
_PARALLEL_COS    = 0.85


def snap_walls_to_polygon(
    walls: list[Wall], polygon: list[list[float]], tol: float = 400.0
) -> list[Wall]:
    """Lukitsee seinien päätepisteet lähimpään polygonin nurkkaan."""
    poly_pts = [np.array(p, dtype=float) for p in polygon]
    result = []
    for wall in walls:
        new_axis = []
        for pt_raw in wall.axis:
            pt = np.array(pt_raw, dtype=float)
            dists = [float(np.linalg.norm(pt - pp)) for pp in poly_pts]
            best_d = min(dists)
            if best_d < tol:
                snapped = poly_pts[dists.index(best_d)]
                new_axis.append([round(float(snapped[0]), 1), round(float(snapped[1]), 1)])
            else:
                new_axis.append(pt_raw)
        result.append(wall.model_copy(update={"axis": new_axis}))
    return result


def build_room_polygon(walls: list[Wall]) -> list[list[float]] | None:
    """Huonepolygoni seinien päätepisteiden ja tarkkojen leikkauspisteiden perusteella."""
    if len(walls) < 3:
        return None

    # Primääri: corner_snap-vaiheen jälkeiset seinäpäätepisteet
    raw: list[np.ndarray] = []
    for w in walls:
        if len(w.axis) >= 2:
            raw.append(np.array(w.axis[0], dtype=float))
            raw.append(np.array(w.axis[1], dtype=float))

    # Sekundääri: leikkauspisteet vain kun MOLEMMAT seinät loppuvat lähelle
    for i, wa in enumerate(walls):
        for j in range(i + 1, len(walls)):
            wb = walls[j]
            pt = _wall_intersection(wa, wb)
            if pt is not None and _near_endpoint(pt, wa, _BOTH_ENDS_DIST) and _near_endpoint(pt, wb, _BOTH_ENDS_DIST):
                raw.append(pt)

    corners = _cluster(raw, _CORNER_SNAP_TOL)
    if len(corners) < 3:
        return None

    arr = np.array(corners)
    # Konveksi kuori: ei itseleikkaa (toisin kuin kulmajärjestys keskipisteen ympäri),
    # ja sisäseinien päätepisteet jäävät automaattisesti kuoren sisälle → ulkoraja.
    try:
        from scipy.spatial import ConvexHull
        poly = arr[ConvexHull(arr).vertices]
    except Exception:
        centre = arr.mean(axis=0)
        angles = np.arctan2(arr[:, 1] - centre[1], arr[:, 0] - centre[0])
        poly = arr[np.argsort(angles)]
    poly = _remove_collinear(poly, tol_deg=4.0)

    if len(poly) < 3:
        return None

    return [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in poly]


# ── apufunktiot ────────────────────────────────────────────────────────────────

def _wall_intersection(wa: Wall, wb: Wall) -> np.ndarray | None:
    if len(wa.axis) < 2 or len(wb.axis) < 2:
        return None
    p0a = np.array(wa.axis[0], dtype=float)
    p1a = np.array(wa.axis[1], dtype=float)
    p0b = np.array(wb.axis[0], dtype=float)
    p1b = np.array(wb.axis[1], dtype=float)
    da = p1a - p0a; db = p1b - p0b
    la = float(np.linalg.norm(da)); lb = float(np.linalg.norm(db))
    if la < 1.0 or lb < 1.0:
        return None
    ua = da / la; ub = db / lb
    if abs(float(np.dot(ua, ub))) > _PARALLEL_COS:
        return None
    A = np.array([[ua[0], -ub[0]], [ua[1], -ub[1]]])
    b_vec = p0b - p0a
    det = float(np.linalg.det(A))
    if abs(det) < 1e-6:
        return None
    t = float(np.linalg.solve(A, b_vec)[0])
    return p0a + t * ua


def _near_endpoint(pt: np.ndarray, wall: Wall, tol: float) -> bool:
    if len(wall.axis) < 2:
        return False
    return (float(np.linalg.norm(pt - np.array(wall.axis[0], dtype=float))) < tol or
            float(np.linalg.norm(pt - np.array(wall.axis[1], dtype=float))) < tol)


def _cluster(pts: list[np.ndarray], tol: float) -> list[np.ndarray]:
    used = [False] * len(pts)
    out: list[np.ndarray] = []
    for i, p in enumerate(pts):
        if used[i]:
            continue
        group = [p]; used[i] = True
        for j in range(i + 1, len(pts)):
            if not used[j] and float(np.linalg.norm(p - pts[j])) < tol:
                group.append(pts[j]); used[j] = True
        out.append(np.mean(group, axis=0))
    return out


def _remove_collinear(poly: np.ndarray, tol_deg: float = 4.0) -> np.ndarray:
    cos_tol = np.cos(np.radians(180.0 - tol_deg))
    keep = []
    n = len(poly)
    for i in range(n):
        prev = poly[(i - 1) % n]
        curr = poly[i]
        nxt  = poly[(i + 1) % n]
        d1 = curr - prev; d2 = nxt - curr
        l1 = float(np.linalg.norm(d1)); l2 = float(np.linalg.norm(d2))
        if l1 < 1.0 or l2 < 1.0:
            continue
        if float(np.dot(d1 / l1, d2 / l2)) < cos_tol:
            keep.append(curr)
    return np.array(keep) if keep else poly

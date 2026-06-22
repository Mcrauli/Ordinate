"""Ortogonaalinen suoristus (Manhattan-world).

Asunnot ovat lähes aina suorakulmaisia, mutta keilaus tuottaa seinät pienessä
(usein satunnaisessa) kierrossa ja kukin seinä hieman eri kulmassa. Tämä etsii
pistepilven yhden hallitsevan kiertokulman ja snäppää jokaisen seinän lähimpään
kahdesta kohtisuorasta suunnasta (θ tai θ+90°). Vain ±tol asteen sisällä olevat
suoristetaan — selvästi vinot seinät (esim. viistot) jätetään rauhaan.

Sisään: list[Wall] → ulos: list[Wall] (akselit kierretty keskipisteen ympäri).
"""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import Wall

_SNAP_TOL_DEG = 22.0   # ° — tätä lähempänä perhesuuntaa olevat snäpätään


def _wall_angle(wall: Wall) -> float | None:
    p0, p1 = np.array(wall.axis[0]), np.array(wall.axis[1])
    d = p1 - p0
    if float(np.hypot(d[0], d[1])) < 1.0:
        return None
    return float(np.arctan2(d[1], d[0]))


def dominant_angle(walls: list[Wall]) -> float | None:
    """Hallitseva kiertokulma [0, π/2), pituuspainotettu ympyräkeskiarvo.

    Kahden kohtisuoran perheen suunnat osuvat samaan arvoon mod 90°, joten
    kulma kerrotaan 4:llä (jakso π/2 → 2π) ympyräkeskiarvoa varten.
    """
    sin_sum = cos_sum = 0.0
    for w in walls:
        a = _wall_angle(w)
        if a is None:
            continue
        length = float(np.hypot(w.axis[1][0] - w.axis[0][0], w.axis[1][1] - w.axis[0][1]))
        sin_sum += length * np.sin(4.0 * a)
        cos_sum += length * np.cos(4.0 * a)
    if sin_sum == 0.0 and cos_sum == 0.0:
        return None
    return float(np.arctan2(sin_sum, cos_sum) / 4.0)


def regularize_orthogonal(walls: list[Wall], drop_skew: bool = True) -> list[Wall]:
    """Snäppää seinät kahteen kohtisuoraan suuntaan keskipisteen ympäri.

    Asunto on Manhattan-world: seinä joka jää yli _SNAP_TOL_DEG päähän
    molemmista perhesuunnista on virhedetektio (vino roskaseinä) ja
    pudotetaan kun ``drop_skew``.
    """
    if len(walls) < 2:
        return walls
    theta = dominant_angle(walls)
    if theta is None:
        return walls

    tol = np.radians(_SNAP_TOL_DEG)
    out: list[Wall] = []
    for w in walls:
        a = _wall_angle(w)
        if a is None:
            out.append(w)
            continue
        # Kandidaattisuunnat: θ, θ+90°, θ+180°, θ+270° (akseli on suuntaamaton)
        best_dir = None
        best_diff = tol
        for k in range(4):
            cand = theta + k * (np.pi / 2.0)
            diff = abs(_angle_wrap(a - cand))
            if diff < best_diff:
                best_diff = diff
                best_dir = cand
        if best_dir is None:
            if not drop_skew:
                out.append(w)  # liian vino → ei snäppiä
            continue           # drop_skew: pudota vino roskaseinä

        p0 = np.array(w.axis[0], dtype=float)
        p1 = np.array(w.axis[1], dtype=float)
        mid = 0.5 * (p0 + p1)
        half = 0.5 * float(np.linalg.norm(p1 - p0))
        u = np.array([np.cos(best_dir), np.sin(best_dir)])
        n0 = mid - half * u
        n1 = mid + half * u
        out.append(w.model_copy(update={"axis": [
            [round(float(n0[0]), 1), round(float(n0[1]), 1)],
            [round(float(n1[0]), 1), round(float(n1[1]), 1)],
        ]}))
    return out


def _angle_wrap(a: float) -> float:
    """Kääri kulma välille [-π, π]."""
    return float((a + np.pi) % (2.0 * np.pi) - np.pi)

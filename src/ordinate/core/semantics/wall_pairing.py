"""Seinien paksuuden laskenta geometrisesti detektoinnin jälkeen.

Kaksi strategiaa:
  1. Geometrinen paritus: etsii rinnakkaiset seinät mallista.
     Jos kaksi seinää on lähes rinnakkaisia ja lähellä toisiaan (50–600 mm),
     ne ovat todennäköisesti saman seinän kaksi pintaa → paksuus = etäisyys.

  2. Arkkitehtuurinen oletus: jos paritus epäonnistuu, käytetään seinäpituuden
     mukaista vakiota: pitkä seinä (>5 m) = 300 mm, lyhyt = 200 mm.

Tämä parantaa erityisesti yksipuolisista skannauksista (Matterport) saatuja
seinämittoja, joissa RANSAC-paritus puuttuu kokonaan.
"""
from __future__ import annotations

import numpy as np

from ordinate.schemas.model import Wall


# Oletuspaksuudet jos paria ei löydy
_LONG_WALL_THRESHOLD_MM = 5_000.0   # yli tämän → ulkoseinä → 300 mm
_THICKNESS_LONG = 300.0
_THICKNESS_SHORT = 200.0

_MIN_PAIR_DIST_MM = 50.0
_MAX_PAIR_DIST_MM = 600.0
_MAX_PARALLEL_CROSS = 0.15   # sin(kulmasta) — alle 9°
_MIN_OVERLAP_RATIO = 0.25    # overlap / lyhyemmän pituus


def _is_measured(w: Wall) -> bool:
    return w.source.notes == "thickness_measured"


def refine_wall_thicknesses(walls: list[Wall]) -> list[Wall]:
    """Parittaa rinnakkaiset seinät ja laskee paksuuden geometrisesti."""
    if not walls:
        return walls

    axes = [_parse_axis(w) for w in walls]
    paired: set[int] = set()
    result = list(walls)

    for i, (p0, p1, d, length, mid) in enumerate(axes):
        if i in paired or _is_measured(walls[i]):
            continue   # jo mitattu RANSAC-parilla

        n = np.array([-d[1], d[0]])   # XY-normaali

        best_dist: float | None = None
        best_j: int | None = None

        for j, (p0_2, p1_2, d2, length2, mid2) in enumerate(axes):
            if j == i or j in paired:
                continue

            # Rinnakkaisuus
            cross = abs(float(np.cross(d, d2)))
            if cross > _MAX_PARALLEL_CROSS:
                continue

            # Etäisyys normaalin suuntaan
            dist = abs(float(np.dot(mid2 - mid, n)))
            if not (_MIN_PAIR_DIST_MM <= dist <= _MAX_PAIR_DIST_MM):
                continue

            # XY-overlapp akselin suuntaan
            overlap = _axis_overlap(p0, p1, p0_2, p1_2, d)
            shorter = min(length, length2)
            if shorter > 0 and overlap / shorter < _MIN_OVERLAP_RATIO:
                continue

            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_j = j

        if best_j is not None:
            paired.add(i)
            paired.add(best_j)
            t = round(best_dist, 1)
            result[i] = walls[i].model_copy(update={"thickness": t})
            result[best_j] = walls[best_j].model_copy(update={"thickness": t})

    # Arkkitehtuuriset oletukset parittomille seinille (ei mitattu eikä löytynyt paria)
    for i, w in enumerate(result):
        if not _is_measured(w) and i not in paired:
            length = axes[i][3]
            if length > _LONG_WALL_THRESHOLD_MM:
                default = _THICKNESS_LONG   # ulkoseinä 300 mm
            elif length > 2000:
                default = _THICKNESS_SHORT  # sisäseinä 200 mm
            else:
                default = 120.0             # väliseinä 120 mm
            result[i] = w.model_copy(update={"thickness": default})

    return result


# --------------------------------------------------------------------------- #

def _parse_axis(w: Wall) -> tuple:
    p0 = np.array(w.axis[0], dtype=float)
    p1 = np.array(w.axis[1], dtype=float)
    vec = p1 - p0
    length = float(np.linalg.norm(vec))
    d = vec / length if length > 0 else np.array([1.0, 0.0])
    mid = (p0 + p1) / 2
    return p0, p1, d, length, mid


def _axis_overlap(
    p0: np.ndarray, p1: np.ndarray,
    p0_2: np.ndarray, p1_2: np.ndarray,
    d: np.ndarray,
) -> float:
    """Päällekkäisyys yhteisellä projektiolla akselin suuntaan."""
    proj = lambda pt: float(np.dot(pt - p0, d))
    a0, a1 = 0.0, float(np.dot(p1 - p0, d))
    b0 = proj(p0_2)
    b1 = proj(p1_2)
    lo = max(min(a0, a1), min(b0, b1))
    hi = min(max(a0, a1), max(b0, b1))
    return max(0.0, hi - lo)

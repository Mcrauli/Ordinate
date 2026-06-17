"""Kulmakorjaus: yhdistää seinät kulmiin snäppäämällä ja jatkamalla akseleita."""
from __future__ import annotations

import numpy as np

from scan2bim.schemas.model import Wall

_MAX_EXTEND = 1500.0      # mm — kuinka paljon seinää voidaan jatkaa leikkauspisteeseen
_MAX_SNAP   = 500.0       # mm — T-liitoksen snap-etäisyys (leikkauspiste seinän sisällä)
_PARALLEL_COS_MAX = 0.70  # |cos| > tämä → rinnakkaiset, ohitetaan


def snap_corners(walls: list[Wall]) -> list[Wall]:
    """Snäppää ja jatkaa seinäakseleita leikkauspisteisiin."""
    if len(walls) < 2:
        return walls

    axes: list[list[list[float]]] = [[list(w.axis[0]), list(w.axis[1])] for w in walls]
    n = len(walls)
    for i in range(n):
        for j in range(i + 1, n):
            _try_connect(axes, i, j)

    return [walls[i].model_copy(update={"axis": axes[i]}) for i in range(n)]


def _try_connect(axes: list[list[list[float]]], i: int, j: int) -> None:
    p0a = np.array(axes[i][0], dtype=float)
    p1a = np.array(axes[i][1], dtype=float)
    p0b = np.array(axes[j][0], dtype=float)
    p1b = np.array(axes[j][1], dtype=float)

    da = p1a - p0a
    db = p1b - p0b
    len_a = float(np.linalg.norm(da))
    len_b = float(np.linalg.norm(db))
    if len_a < 1.0 or len_b < 1.0:
        return

    ua = da / len_a
    ub = db / len_b

    if abs(float(np.dot(ua, ub))) > _PARALLEL_COS_MAX:
        return

    pt, ta, tb = _intersection_params(p0a, ua, p0b, ub)
    if pt is None:
        return

    # --- Seinä A ---
    # ta < 0:       leikkauspiste p0a:n takana → jatka p0a
    # ta > len_a:   leikkauspiste p1a:n edessä → jatka p1a
    # muuten:       T-liitos, snäppää B:n lähin pääte; leikkaa A:n pää liitokseen jos lähellä
    if ta < 0 and abs(ta) <= _MAX_EXTEND:
        axes[i][0] = _fmt(pt)
    elif ta > len_a and (ta - len_a) <= _MAX_EXTEND:
        axes[i][1] = _fmt(pt)
    else:
        # T-liitos A:ssa — snäppää B:n lähin pääte kohtisuoraan A:han
        _snap_endpoint_to_wall(axes, j, p0a, ua, len_a)

    # --- Seinä B ---
    if tb < 0 and abs(tb) <= _MAX_EXTEND:
        axes[j][0] = _fmt(pt)
        # T-liitos A:ssa ja B:n pää on juuri liitoksen vieressä → leikkaa A:n ylijäämä
        if abs(tb) < 10.0 and 0.0 < ta < len_a:
            _clip_overshoot(axes, i, ta, len_a, pt)
    elif tb > len_b and (tb - len_b) <= _MAX_EXTEND:
        axes[j][1] = _fmt(pt)
        if abs(tb - len_b) < 10.0 and 0.0 < ta < len_a:
            _clip_overshoot(axes, i, ta, len_a, pt)
    else:
        _snap_endpoint_to_wall(axes, i, p0b, ub, len_b)


_MAX_OVERSHOOT = 100.0  # mm — seinän pää saa ylittää T-liitoksen enintään tämän verran


def _clip_overshoot(
    axes: list[list[list[float]]],
    k: int,
    ta: float,
    len_a: float,
    pt: np.ndarray,
) -> None:
    """Leikkaa seinän k pään T-liitospisteeseen jos se ylittää sen enintään _MAX_OVERSHOOT."""
    p0_near = len_a - ta  # etäisyys p1:een
    p1_near = ta           # etäisyys p0:aan
    if p0_near <= _MAX_OVERSHOOT and p0_near >= 0.0:
        axes[k][1] = _fmt(pt)
    elif p1_near <= _MAX_OVERSHOOT and p1_near >= 0.0:
        axes[k][0] = _fmt(pt)


def _snap_endpoint_to_wall(
    axes: list[list[list[float]]],
    k: int,
    wall_origin: np.ndarray,
    wall_dir: np.ndarray,
    wall_len: float,
) -> None:
    """Snäppää seinän k lähin pääte kohtisuoraan seinä-viivalle (T-liitos)."""
    _TOL = 50.0
    for idx in range(2):
        ep = np.array(axes[k][idx], dtype=float)
        t = float(np.dot(ep - wall_origin, wall_dir))
        if t < -_TOL or t > wall_len:
            continue
        t = max(0.0, t)
        proj = wall_origin + t * wall_dir
        dist = float(np.linalg.norm(ep - proj))
        if dist <= _MAX_SNAP:
            axes[k][idx] = _fmt(proj)
            return


def _intersection_params(
    p1: np.ndarray, d1: np.ndarray,
    p2: np.ndarray, d2: np.ndarray,
) -> tuple[np.ndarray | None, float, float]:
    """Palauttaa (leikkauspiste, ta, tb). None jos rinnakkaiset."""
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
    b = np.array([p2[0] - p1[0], p2[1] - p1[1]])
    det = float(np.linalg.det(A))
    if abs(det) < 1e-6:
        return None, 0.0, 0.0
    ts = np.linalg.solve(A, b)
    ta, tb = float(ts[0]), float(ts[1])
    return p1 + ta * d1, ta, tb


def _fmt(pt: np.ndarray) -> list[float]:
    return [round(float(pt[0]), 1), round(float(pt[1]), 1)]

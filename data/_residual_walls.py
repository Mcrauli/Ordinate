"""Mita seinamaista jaa mallin ULKOPUOLELLE.

Instanssikattavuus kertoo etta puolet GT-seinista puuttuu, muttei sita onko
niita ylipaataan mahdollista loytaa: naytetaanko ne pilvessa yhtenaisina
pystypintoina vai vain sirontana. Tama poistaa mallin seinien lunastamat
pisteet ja etsii jaannoksesta suoraviivaiset pystyrakenteet - sama kysymys
kuin palkeissa ("mika suure oikeasti mitataan"), seinapuolella.

Ajo: _residual_walls.py <model.json> <cloud|coord.npy> [class.npy]
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

import numpy as np
from scipy.ndimage import label as cc

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _soffit_probe import load_pts  # noqa: E402

_CELL = 100.0
_BAND = 80.0
_MIN_PTS = 12         # pisteita solussa jotta se on pintaa
_MIN_LEN = 1000.0
_MIN_ASPECT = 4.0
_REG = {0: "None", 1: "Ceiling", 4: "Floor", 5: "Wall", 6: "Drywall", 8: "Parapet",
        9: "Beam", 10: "Column", 11: "Stair", 13: "Window", 14: "DoorRO",
        15: "Facade", 17: "TGA"}


def main(mj: str, cloud: str, class_npy: str | None = None) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = load_pts(cloud)
    C = np.load(class_npy).ravel() if class_npy else None
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=zf + 2700)
    # vyotarokaista: kalusteet ja katto pois, seinat mukana
    band = (P[:, 2] > zf + 900) & (P[:, 2] < zf + 0.6 * (zc - zf))
    Q = P[band]
    G = C[band] if C is not None else None

    claimed = np.zeros(len(Q), bool)
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 500.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = Q[:, :2] - a
        s, t = d @ u, d @ n
        claimed |= (s > -200.0) & (s < L + 200.0) & (np.abs(t) < w["thickness"] / 2.0 + _BAND)

    R = Q[~claimed]
    print(f"kaistassa {len(Q):,} pistetta, mallin lunastamia {int(claimed.sum()):,} "
          f"({claimed.mean():.1%}), jaannos {len(R):,}")
    if len(R) < 100:
        return

    origin = R[:, :2].min(0)
    ij = np.floor((R[:, :2] - origin) / _CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    cnt = np.bincount(ij[:, 0] * ny + ij[:, 1], minlength=nx * ny).reshape(nx, ny)
    surf = cnt >= _MIN_PTS
    lab, ncomp = cc(surf, structure=np.ones((3, 3), dtype=int))
    print(f"jaannossoluja {int(surf.sum()):,}, komponentteja {ncomp}")

    rows = []
    key = ij[:, 0] * ny + ij[:, 1]
    for k in range(1, ncomp + 1):
        cx, cy = np.nonzero(lab == k)
        if len(cx) < 8:
            continue
        xy = np.column_stack([cx, cy]).astype(float) * _CELL + origin + _CELL / 2
        c = xy.mean(0)
        A = xy - c
        _, V = np.linalg.eigh(A.T @ A / len(A))
        L = float((A @ V[:, 1]).ptp()) + _CELL
        W = float((A @ V[:, 0]).ptp()) + _CELL
        if L < _MIN_LEN or L / max(W, 1.0) < _MIN_ASPECT:
            continue
        sel = np.isin(key, cx * ny + cy)
        gt = ""
        if G is not None and sel.any():
            g = G[~claimed][sel]
            tot = len(g)
            gt = "  ".join(f"{_REG.get(int(v), v)}={100 * n2 / tot:.0f}%"
                           for v, n2 in collections.Counter(g.tolist()).most_common(3))
        rows.append((int(sel.sum()), L, W, c, gt))

    rows.sort(key=lambda r: -r[1])
    print(f"\n{'n':>8s} {'pituus':>7s} {'lev':>5s} {'x':>8s} {'y':>8s}  GT-jakauma")
    for n, L, W, c, gt in rows[:20]:
        print(f"{n:8d} {L:7.0f} {W:5.0f} {c[0]:8.0f} {c[1]:8.0f}  {gt}")
    wallish = [r for r in rows if r[4].startswith(("Wall", "Drywall", "Parapet", "Facade"))]
    print(f"\nsuoraviivaisia jaannosrakenteita {len(rows)}, "
          f"joista GT-seinavoittoisia {len(wallish)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])

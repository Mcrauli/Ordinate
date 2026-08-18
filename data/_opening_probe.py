"""Miksi mallinnetulla seinalla oleva GT-aukko jaa loytymatta.

`_opening_view.py` erottaa kaksi eri vikaa: aukko seinalla jota ei ole
mallinnettu (ei aukkodetektorin vika) ja aukko mallinnetulla seinalla. Tama
tutkii jalkimmaiset: onko pilvessa ylipaataan reika aukon kohdalla.

Tulostaa jokaiselle GT-aukolle seinapinnan miehityksen aukon kohdalla ja sen
vieressa - jos aukon kohta on yhta tayde kuin seina, reikaa ei ole nakyvissa
eika mikaan saanto loyda sita.

Ajo: _opening_probe.py <model.json> <coord.npy> <class.npy>
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

_OPEN = (7, 12, 13, 14)
_MIN_PTS = 500
_FACE = 60.0       # mm — kaista seinapinnan ymparilla
_COL = 100.0       # mm — sarakkeen leveys
_ZLO, _ZHI = 200.0, 2000.0   # aukon korkeuskaista lattiasta


def main(mj: str, coord_npy: str, class_npy: str) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    I = np.load(pathlib.Path(class_npy).with_name("instance.npy")).ravel()
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    gt = np.isin(C, _OPEN)

    inst = []
    for i in np.unique(I[gt]):
        q = P[gt][I[gt] == i]
        if len(q) < _MIN_PTS:
            continue
        inst.append((int(i), q[:, :2].mean(0), len(q),
                     float(np.hypot(*(q[:, :2].max(0) - q[:, :2].min(0))))))

    zb = (P[:, 2] > zf + _ZLO) & (P[:, 2] < zf + _ZHI)
    xy = P[zb][:, :2]

    print(f"{'inst':>6s} {'seina':10s} {'along':>7s} {'lev':>6s} "
          f"{'aukossa':>8s} {'vieressa':>9s}  paatelma")
    for i, c, n, w in sorted(inst, key=lambda t: -t[2]):
        best = None
        for wl in m["walls"]:
            a = np.array(wl["axis"][0], float)
            b = np.array(wl["axis"][1], float)
            L = float(np.linalg.norm(b - a))
            if L < 1.0:
                continue
            u = (b - a) / L
            s = float(np.clip((c - a) @ u, 0.0, L))
            d = float(np.linalg.norm(c - (a + u * s)))
            if best is None or d < best[0]:
                best = (d, wl, L, a, u, s)
        d, wl, L, a, u, s0 = best
        if d > 500.0:
            continue
        nrm = np.array([-u[1], u[0]])
        rel = xy - a
        ss, tt = rel @ u, rel @ nrm
        face = np.abs(np.abs(tt) - wl["thickness"] / 2.0) < _FACE

        def fill(lo: float, hi: float) -> float:
            cols = np.arange(lo, hi, _COL)
            if len(cols) < 2:
                return 0.0
            k = np.clip(((ss - lo) / _COL).astype(np.int64), 0, len(cols) - 1)
            sel = face & (ss >= lo) & (ss < hi)
            if not sel.any():
                return 0.0
            occ = np.bincount(k[sel], minlength=len(cols)) >= 3
            return float(occ.mean())

        half = max(w / 2.0, 300.0)
        f_in = fill(s0 - half, s0 + half)
        f_side = 0.5 * (fill(s0 - 3 * half, s0 - half) + fill(s0 + half, s0 + 3 * half))
        why = ("ei reikaa pilvessa" if f_in > 0.6 * max(f_side, 1e-9) and f_in > 0.4
               else "seina itsekin tyhja" if f_side < 0.3
               else "REIKA NAKYY - detektori ei loydä")
        print(f"{i:6d} {wl['id']:10s} {s0:7.0f} {w:6.0f} {f_in:8.2f} {f_side:9.2f}  {why}")


if __name__ == "__main__":
    main(*sys.argv[1:4])

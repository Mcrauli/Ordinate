"""Onko seinan kohdalla ENEMMAN pystypintaa kuin sen vierella?

Jokainen tahan asti kokeiltu erottelija on mitannut TASOA (tuki, jatkuvuus,
kate, komponentin koko) ja jokainen on kaatunut siihen etta taso riippuu
skannista: sama luku tarkoittaa eri asiaa 1.8 m kellarissa ja 10 m hallissa.

Tama mittaa SUHDETTA saman pilven sisalla: pystypintapisteita seinan omalla
pinnalla vs. sama mitta kontrollietaisyydella (0.75 ja 1.25 m sivussa, samat
sarakkeet). Aito seina erottuu ymparistostaan; putkimetsan lapi vedetty viiva
ei, koska putkia on yhta paljon joka puolella. Suhde on dimensioton eika
riipu keilaustiheydesta, huonekorkeudesta eika pistevalista.

Kaytto: _contrast_probe.py <model.json> <wallish.npz> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_BAND = 80.0
_CTRL = (750.0, 1250.0)
_MIN_LEN = 2000.0


def wall_contrast(a, b, thickness, xy_all, xy_wallish):
    """(kontrasti, pintapisteita) — None kun seina on liian lyhyt."""
    L = float(np.linalg.norm(b - a))
    if L < _MIN_LEN:
        return None
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    half = thickness / 2.0

    def count(pts, off):
        d = pts - a
        s, t = d @ u, d @ n
        sel = (s > 0) & (s < L) & (np.abs(np.abs(t) - off) < _BAND)
        return int(sel.sum())

    on = count(xy_wallish, half)
    ctrl = [count(xy_wallish, half + c) for c in _CTRL]
    base = float(np.median(ctrl))
    return (on + 1.0) / (base + 1.0), on


def main(model_json: str, wallish_npz: str, name: str = "") -> None:
    z = np.load(wallish_npz)
    q = z["q"].astype(np.float64)
    xy_all = q[:, :2]
    xy_w = q[z["m"]][:, :2]
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))

    out = []
    for x in m["walls"]:
        ax = x.get("axis") or []
        if len(ax) < 2:
            continue
        r = wall_contrast(np.asarray(ax[0], float)[:2],
                          np.asarray(ax[-1], float)[:2],
                          float(x["thickness"]), xy_all, xy_w)
        if r is None:
            continue
        out.append((x["id"], r[0], r[1],
                    float(np.linalg.norm(np.asarray(ax[-1], float)[:2]
                                         - np.asarray(ax[0], float)[:2]))))
    if not out:
        print(f"{name or model_json}: ei mitattavia seinia")
        return
    c = np.array([o[1] for o in out])
    print(f"{name or model_json:14s} seinia {len(out):4d}  kontrasti "
          f"p10 {np.percentile(c,10):5.2f} med {np.median(c):5.2f} "
          f"p90 {np.percentile(c,90):6.2f}   alle 1.5: {float((c<1.5).mean()):.2f}")
    return out


if __name__ == "__main__":
    main(*sys.argv[1:])

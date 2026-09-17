"""Miksi keilatun myymälän aukko jää löytymättä tai sen korkeus on väärin.

`_opening_place_qa.py` kertoi (17.9.2026): 5/10 aukkoa löytyy, ja löytyneistä
kolmella korkeus on +99…+127 mm liian suuri. Tämä erottelee jokaiselle GT-
aukolle syyn datasta, ei arvaamalla:

  isäntä   : onko mallissa seinä aukon kohdalla ja kuinka lähellä sen päätä
             aukko on (seinän pään aukko on tunnettu sokea kohta)
  reikä    : näkyykö pilvessä reikä (miehitys aukossa vs sivuilla)
  ylälaita : missä tiheys oikeasti hyppää aukon yläpuolella, verrattuna GT:hen

Käyttö: _opening_store_probe.py <model.json> <store_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def _seg_dist(p, a, b):
    ab = b - a
    L2 = float(ab @ ab)
    t = 0.0 if L2 < 1 else float(np.clip((p - a) @ ab / L2, 0, 1))
    return float(np.linalg.norm(p - (a + t * ab))), t * L2 ** 0.5, L2 ** 0.5


def main(model_json: str, store_dir: str) -> None:
    d = Path(store_dir)
    g = json.loads((d / "gt.json").read_text(encoding="utf-8"))
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    P = np.load(d / "coord.npy").astype(np.float64)
    if float(np.ptp(P[:, 0])) < 500.0:
        P = P * 1000.0
    floor = float(g["floor_z"])
    print(f"{'GT':>2} {'tyyppi':6} {'isäntä':>7} {'päähän':>7} {'reikä sis/sivu':>15} "
          f"{'GT ylä':>7} {'mitattu ylä':>11}")
    for i, o in enumerate(g["openings"]):
        c = np.array(o["center"], float)
        gw = min(g["walls"], key=lambda w: _seg_dist(c, np.array(w["axis"][0], float),
                                                      np.array(w["axis"][1], float))[0])
        a, b = np.array(gw["axis"][0], float), np.array(gw["axis"][1], float)
        u = (b - a) / np.linalg.norm(b - a)
        n = np.array([-u[1], u[0]])
        # mallin isäntäseinä: samansuuntainen, lähin
        best = None
        for w in m["walls"]:
            wa, wb = np.array(w["axis"][0], float), np.array(w["axis"][1], float)
            if np.linalg.norm(wb - wa) < 1:
                continue
            wu = (wb - wa) / np.linalg.norm(wb - wa)
            if abs(float(wu @ u)) < 0.985:
                continue
            dist, s, L = _seg_dist(c, wa, wb)
            if best is None or dist < best[0]:
                best = (dist, min(s, L - s))
        host = "puuttuu" if best is None or best[0] > 800 else f"{best[0]:.0f} mm"
        to_end = "—" if best is None or best[0] > 800 else f"{best[1]:.0f} mm"

        rel = P[:, :2] - c
        along = rel @ u
        perp = rel @ n
        z = P[:, 2] - floor
        half = o["width"] / 2.0
        near = np.abs(perp) <= gw["thickness"] / 2.0 + 100.0
        zin = (z > o["sill"] + 100) & (z < o["sill"] + o["height"] - 100)
        inside = near & zin & (np.abs(along) < half - 100)
        side = near & zin & (np.abs(along) > half + 100) & (np.abs(along) < half + 1100)
        w_in = max((o["width"] - 200) / 1000.0, 0.1)
        dens_in = inside.sum() / w_in
        dens_side = side.sum() / 2.0
        hole = f"{dens_in:7.0f}/{dens_side:<7.0f}"

        head = o["sill"] + o["height"]
        col = near & (np.abs(along) < half / 2)
        zz = z[col & (z > head - 300) & (z < head + 300)]
        measured = "—"
        if len(zz) > 50:
            hist, edges = np.histogram(zz, bins=np.arange(head - 300, head + 320, 20))
            above = hist[edges[:-1] >= head + 100]
            ref = float(np.median(above)) if len(above) else 0.0
            if ref > 0:
                k = np.argmax(hist >= 0.5 * ref)
                measured = f"{edges[k]:.0f} mm"
        print(f"{i:2d} {o['type']:6s} {host:>7} {to_end:>7} {hole:>15} {head:7.0f} {measured:>11}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

"""Seinainstanssit ILMAN ground truthia: montako aitoa seinalinjaa on mallissa?

AGENTS.md: "PISTEKATTAVUUS PIILOTTAA PUUTTUVAT SEINAT — MITTAA INSTANSSIT" ja
"Optimoi instanssikattavuutta, ala pistekattavuutta". `_wall_inst_qa.py` tekee
sen GT-instansseista; asiakaskohteessa niita ei ole.

Tama rakentaa instanssit pilvesta: seinamaiset pystypintapisteet ryhmitellaan
yhtenaisiin komponentteihin ja jokaiseen sovitetaan jana. Pitka ohut jana on
seinalinja. Kattavuus = kuinka moni niista on jonkin mallin seinan kaistassa,
tarkkuus = kuinka moni mallin seinista osuu johonkin niista.

TARKEA ERO PISTEKATTAVUUTEEN: rakennuksen halki vedetty valeseina lakaisee
pisteita monelta linjalta ja saa siksi korkean PISTEkattavuuden, mutta se ei
lunasta yhtaan linjaa kokonaan. Instanssimittari ei palkitse lakaisua.

Kaytto: _wall_inst_nogt.py <model.json> <wallish.npz> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_CELL = 150.0        # mm — ruudukko komponentteihin
_MIN_LEN = 1500.0    # mm — lyhyempi ei ole seinalinja
_MAX_WIDTH = 400.0   # mm — leveampi on laikku, ei linja
_MIN_PTS = 30
_BAND = 150.0        # mm — kuinka lahelta mallin seinan on kuljettava
_HIT_FRAC = 0.50     # osuus linjan pituudesta jonka mallin on katettava


def line_instances(W: np.ndarray) -> list:
    """Seinamaisista pisteista sovitetut janat [(a, b, pituus), ...]."""
    from scipy import ndimage

    xy = W[:, :2]
    ij = np.floor(xy / _CELL).astype(np.int64)
    ij -= ij.min(axis=0)
    grid = np.zeros(ij.max(axis=0) + 1, dtype=bool)
    grid[ij[:, 0], ij[:, 1]] = True
    lab, n = ndimage.label(grid, structure=np.ones((3, 3)))
    idx = lab[ij[:, 0], ij[:, 1]]
    out = []
    for k in range(1, n + 1):
        g = xy[idx == k]
        if len(g) < _MIN_PTS:
            continue
        c = g - g.mean(axis=0)
        ev, vec = np.linalg.eigh(np.cov(c.T))
        u = vec[:, -1]
        s = c @ u
        length = float(s.max() - s.min())
        width = float(4.0 * np.sqrt(max(ev[0], 0.0)))
        if length < _MIN_LEN or width > _MAX_WIDTH:
            continue
        mid = g.mean(axis=0)
        out.append((mid + u * s.min(), mid + u * s.max(), length))
    return out


def score(model_walls, W: np.ndarray):
    """(kattavuus, tarkkuus, linjoja, seinia) instansseina."""
    lines = line_instances(W)
    walls = []
    for w in model_walls:
        ax = w.get("axis") if isinstance(w, dict) else getattr(w, "axis", None)
        if not ax or len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 800.0:
            continue
        walls.append((a, (b - a) / L, L))
    if not lines or not walls:
        return 0.0, 0.0, len(lines), len(walls)

    covered = np.zeros(len(lines), dtype=bool)
    used = np.zeros(len(walls), dtype=bool)
    for li, (la, lb, L) in enumerate(lines):
        steps = max(int(L / 250.0), 2)
        pts = la + (lb - la) * np.linspace(0.0, 1.0, steps)[:, None]
        for wi, (a, u, wl) in enumerate(walls):
            d = pts - a
            s, t = d @ u, d @ np.array([-u[1], u[0]])
            on = (s > -_BAND) & (s < wl + _BAND) & (np.abs(t) < _BAND)
            if on.mean() >= _HIT_FRAC:
                covered[li] = True
                used[wi] = True
    return (float(covered.mean()), float(used.mean()), len(lines), len(walls))


def main(model_json: str, wallish_npz: str, name: str = "") -> None:
    z = np.load(wallish_npz)
    W = z["q"].astype(np.float64)[z["m"]]
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    cov, pre, nl, nw = score(m["walls"], W)
    print(f"{name or model_json:14s} linjoja {nl:4d}  seinia {nw:4d}  "
          f"INSTANSSIkattavuus {cov:.3f}  tarkkuus {pre:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

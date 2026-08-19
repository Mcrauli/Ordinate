"""Aukot GT:ta vasten: Rohbau3D per-piste luokat 7/12/13/14.

Aukkodetektiota ei ollut mitattu totuutta vasten lainkaan - sama tilanne kuin
palkeissa, joissa lahtoluku oli 0.048. Rohbau site_07:ssa on 86 aukko-
instanssia viidessa scenessa, joten kysymys on mitattavissa.

GT-luokat: 14 = Door Rough Opening (oviaukon pielet), 7 = Wall Cutout,
12 = Window Cutout, 13 = Window. Rohbau on runkovaihe, joten ikkunoita ei ole
asennettu ja ikkuna-aukot ovat luokassa 7.

KATTAVUUS : kuinka moni GT-aukkoinstanssi osuu mallin aukkoon.
TARKKUUS  : kuinka moni mallin aukko osuu GT-aukkoon.

Kaytto: _opening_qa.py <model.json> <coord.npy> <class.npy> [instance.npy]
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

_OPEN = (7, 12, 13, 14)
_TOL = 700.0        # mm — sallittu poikkeama aukon keskipisteesta
_MIN_W = 300.0      # mm — tata kapeampi ei ole kuljettava eika mallinnettava aukko
_MIN_H = 300.0      # mm


def _wall_xy(m, o):
    """Aukon keskipiste maailmassa: seinan p0 + position_along + puoli leveytta."""
    w = next((w for w in m["walls"] if w["id"] == o["wall_id"]), None)
    if w is None:
        return None
    a = np.array(w["axis"][0], float)
    b = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(b - a))
    if L < 1.0:
        return None
    u = (b - a) / L
    return a + u * (o["position_along"] + o["width"] / 2.0)


def _real(width: float, height: float) -> bool:
    """Onko GT-instanssi aukko jonka malli voi loytaa.

    Nimittaja EI saa olla pistemaara: `n >= 500` sitoo mittarin skannin
    tiheyteen, jolloin harvempi skanni pudottaa pienet aukot pois nimittajasta
    ja kattavuus NAYTTAA paremmalta ilman etta mikaan parani. Koko on
    fysikaalinen ja mitattavissa samana jokaisesta skannista.
    """
    return width >= _MIN_W and height >= _MIN_H


def main(mj, coord_npy, class_npy, inst_npy=None):
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    if inst_npy is None:
        cand = pathlib.Path(class_npy).with_name("instance.npy")
        inst_npy = str(cand) if cand.exists() else None
    I = np.load(inst_npy).ravel() if inst_npy else None

    gt = np.isin(C, _OPEN)
    ops = m.get("openings", [])
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    print(f"GT-aukkopisteita {int(gt.sum()):,}   mallin aukkoja {len(ops)} "
          f"(ovia {sum(1 for o in ops if o['opening_type'] == 'door')}, "
          f"ikkunoita {sum(1 for o in ops if o['opening_type'] == 'window')})")
    if I is None or not gt.any():
        return

    ids, cnts = np.unique(I[gt], return_counts=True)
    gtc = []
    for i, n in zip(ids, cnts):
        q = P[gt][I[gt] == i]
        gtc.append((int(i), q[:, :2].mean(0), float(q[:, 2].min()), float(q[:, 2].max()), int(n),
                    float(np.hypot(*(q[:, :2].max(0) - q[:, :2].min(0))))))

    det = []
    for o in ops:
        c = _wall_xy(m, o)
        if c is None:
            continue
        det.append((o, c, zf + o["sill_height"], zf + o["sill_height"] + o["opening_height"]))

    found = 0
    print(f"\n{'inst':>6s} {'n':>8s} {'leveys':>7s} {'z':>7s}..{'':>6s} {'lahin malli':>12s}")
    for i, c, z0, z1, n, w in sorted(gtc, key=lambda t: -t[4]):
        best = None
        for o, dc, dz0, dz1 in det:
            d = float(np.linalg.norm(dc - c))
            if best is None or d < best[0]:
                best = (d, o)
        real = _real(w, z1 - z0)
        ok = best is not None and best[0] <= max(_TOL, w / 2.0) and real
        found += bool(ok)
        tag = f"{best[1]['id']} {best[0]:.0f} mm" if best else "-"
        print(f"{i:6d} {n:8,} {w:7.0f} {z0:7.0f}..{z1:6.0f} {tag:>12s}"
              + ("" if ok else "   <== EI LOYDETTY" if real
                 else f"   (alle {_MIN_W:.0f} mm)"))

    big = [g for g in gtc if _real(g[5], g[3] - g[2])]
    print(f"\nKATTAVUUS  GT-aukoista mallissa: {found}/{len(big)} = "
          f"{found / max(len(big), 1):.3f}   "
          f"(alle {_MIN_W:.0f} x {_MIN_H:.0f} mm instanssit ohitettu)")

    hit = 0
    for o, dc, dz0, dz1 in det:
        if any(float(np.linalg.norm(dc - c)) <= max(_TOL, w / 2.0)
               for _, c, z0, z1, n, w in gtc if _real(w, z1 - z0)):
            hit += 1
    print(f"TARKKUUS   mallin aukoista GT-aukolla: {hit}/{max(len(det), 1)} = "
          f"{hit / max(len(det), 1):.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:5])

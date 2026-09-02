"""Mika EROTTAA loytyneet lyhyet seinat puuttuvista? Mitattuna GT:sta.

Karsinta ei ole syy: kaikki kahdeksan karsintaa pois paalta jattaa
scene_07002:n 2-4 m luokan tasan ennalleen (7/21) ja samat kuusi pisinta
puuttuvaa puuttuvat yha. Detektori ei siis tuota niita.

Silloin oikea kysymys ei ole "mika portti poistaa" vaan "mika naissa on
toisin". Tama laskee jokaiselle GT:n seinainstanssille mitattavia
ominaisuuksia ja vertaa LOYTYNEITA ja PUUTTUVIA:

  pisteita        - onko pinta ylipaataan keilattu
  korkeus         - ulottuuko lattiasta kattoon vai onko tynka
  korkeusosuus    - sama suhteessa kerroskorkeuteen (skaalavapaa)
  paksuus-parisuus - nakyyko molemmat pinnat (Wall+Drywall samassa kohdassa)
  naapurietaisyys - onko lahella toista seinaa (kontuuri nakee vain ensimmaisen)

Suhteet, ei tasoja: putken on toimittava milla tahansa keilaustiheydella.

Kaytto: _missing_wall_probe.py <scene_dir> <model.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_STRUCT = (5, 6, 8, 15)     # Wall, Drywall, Parapet, Facade Element
_BAND = 80.0                # sama kaista kuin _wall_inst_qa
_HIT = 0.30                 # sama osumaosuus
_MIN_PTS = 2000


def _model_walls(mj: str):
    m = json.loads(Path(mj).read_text(encoding="utf-8"))
    out = []
    for w in m["walls"]:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        out.append((a, (b - a) / L, L, float(w["thickness"])))
    return out


def _covered(xy: np.ndarray, walls) -> float:
    """Osuus instanssin pisteista jonkin mallin seinan kaistassa."""
    if not len(walls) or not len(xy):
        return 0.0
    hit = np.zeros(len(xy), dtype=bool)
    for a, u, L, th in walls:
        d = xy - a
        s = d @ u
        t = d @ np.array([-u[1], u[0]])
        hit |= (s > -_BAND) & (s < L + _BAND) & (np.abs(np.abs(t) - th / 2.0) < _BAND)
    return float(hit.mean())


def main(scene_dir: str, model_json: str) -> None:
    scene = Path(scene_dir)
    xyz = np.load(scene / "coord.npy").astype(np.float64)
    cls = np.load(scene / "class.npy").ravel()
    inst = np.load(scene / "instance.npy").ravel()
    if np.ptp(xyz[:, 0]) < 500.0:
        xyz = xyz * 1000.0

    z_lo, z_hi = np.percentile(xyz[:, 2], 1), np.percentile(xyz[:, 2], 99)
    storey = float(z_hi - z_lo)
    walls = _model_walls(model_json)

    struct = np.isin(cls, _STRUCT)
    rows = []
    for i in np.unique(inst[struct]):
        sel = struct & (inst == i)
        n = int(sel.sum())
        if n < _MIN_PTS:
            continue
        p = xyz[sel]
        c = p[:, :2] - p[:, :2].mean(axis=0)
        ev, vec = np.linalg.eigh(np.cov(c.T))
        s = c @ vec[:, -1]
        length = float(s.max() - s.min())
        h = float(p[:, 2].max() - p[:, 2].min())
        cov = _covered(p[:, :2], walls)
        rows.append((int(i), length, n, h, h / storey, cov >= _HIT))

    if not rows:
        print("ei instansseja")
        return
    L = np.array([r[1] for r in rows])
    N = np.array([r[2] for r in rows])
    H = np.array([r[3] for r in rows])
    F = np.array([r[4] for r in rows])
    ok = np.array([r[5] for r in rows])
    short = (L >= 1500.0) & (L < 4000.0)

    print(f"{scene.name}: {len(rows)} instanssia, kerroskorkeus {storey/1000:.1f} m")
    for name, sel in (("KAIKKI", np.ones(len(rows), bool)), ("2-4 m", short)):
        if not sel.any():
            continue
        a, b = sel & ok, sel & ~ok
        print(f"  {name}: loytyi {int(a.sum())}, puuttuu {int(b.sum())}")
        for lbl, g in (("loytyi ", a), ("puuttuu", b)):
            if not g.any():
                continue
            print(f"    {lbl}: pisteita med {np.median(N[g]):8.0f}  "
                  f"korkeus med {np.median(H[g])/1000:5.2f} m  "
                  f"korkeusosuus med {np.median(F[g]):.2f}  "
                  f"pituus med {np.median(L[g])/1000:5.2f} m")


if __name__ == "__main__":
    main(*sys.argv[1:])

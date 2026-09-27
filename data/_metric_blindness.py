"""NAKEEKO GT-vapaa mittari lyhyita seinia lainkaan?

Kolmetoista hypoteesia on mitattu ja matriisi on nayttanyt +0.000 joka kerta.
Ennen seuraavaa korjausta on syyta kysya toisin pain: PYSTYYKO mittari
palkitsemaan lyhyiden seinien loytamisesta?

`wall_coverage` laskee osuuden pilven seinamaisista PISTEISTA jotka mallin
kaista kattaa. Pistemaara on verrannollinen seinan PINTA-ALAAN, joten 30 m
perimetriseina omistaa moninkertaisesti sen mita 2 m valiseina. Jos nain on,
kaikkien lyhyiden seinien lisaaminen liikuttaa lukua tuskin lainkaan — ja
silloin koko regressiomatriisi on sokea juuri sille parannukselle jota
haetaan, eika yksikaan lyhyiden seinien korjaus voi koskaan nayttaa hyvalta.

Koe ei kayta detektoria lainkaan. "Malli" rakennetaan GT-instansseista, joten
se on tasmalleen oikea — ja sita rajataan pituuden mukaan:

  vain yli 4 m   = malli joka on loytanyt pitkat seinat ja hukannut lyhyet
  kaikki         = taydellinen malli

Ero naiden valilla on mittarin KOKO LIIKKUMAVARA lyhyiden seinien suhteen.
Jos se on muutama tuhannesosa, mittari ei voi ohjata tata tyota.

Kaytto: _metric_blindness.py <scene_dir> <cloud.ply>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_STRUCT = (5, 6, 8, 15)
_MIN_PTS = 2000


def _gt_walls(scene: Path):
    from ordinate.schemas.model import ElementSource, Wall

    xyz = np.load(scene / "coord.npy").astype(np.float64)
    cls = np.load(scene / "class.npy").ravel()
    inst = np.load(scene / "instance.npy").ravel()
    if np.ptp(xyz[:, 0]) < 500.0:
        xyz = xyz * 1000.0
    struct = np.isin(cls, _STRUCT)
    walls, lens = [], []
    for i in np.unique(inst[struct]):
        sel = struct & (inst == i)
        if sel.sum() < _MIN_PTS:
            continue
        p = xyz[sel]
        xy = p[:, :2]
        cen = xy.mean(axis=0)
        d = xy - cen
        _, vec = np.linalg.eigh(np.cov(d.T))
        u = vec[:, -1]
        t = d @ u
        a, b = cen + u * t.min(), cen + u * t.max()
        L = float(t.max() - t.min())
        if L < 500.0:
            continue
        walls.append(Wall(
            id=f"gt_{len(walls):03d}", confidence=1.0, classification="wall",
            source=ElementSource(method="manual"),
            axis=[[float(a[0]), float(a[1])], [float(b[0]), float(b[1])]],
            height=float(np.ptp(p[:, 2])), thickness=200.0,
            z_min=float(p[:, 2].min())))
        lens.append(L)
    return walls, np.array(lens), xyz


def main(scene_dir: str) -> None:
    from ordinate.core.qa.coverage import wall_scores

    scene = Path(scene_dir)
    walls, lens, xyz = _gt_walls(scene)
    floor = float(np.percentile(xyz[:, 2], 2))
    ceiling = float(np.percentile(xyz[:, 2], 98))
    print(f"{scene.name}: {len(walls)} GT-seinaa, lattia {floor:.0f}, "
          f"katto {ceiling:.0f}")

    subsets = [
        ("vain yli 4 m", lens >= 4000),
        ("yli 2 m", lens >= 2000),
        ("yli 1 m", lens >= 1000),
        ("kaikki", np.ones(len(lens), dtype=bool)),
    ]
    print(f"  {'osajoukko':16s} {'seinia':>7s} {'kattavuus':>10s} "
          f"{'tarkkuus':>9s} {'F1':>7s}")
    prev = None
    for name, m in subsets:
        sub = [w for w, k in zip(walls, m) if k]
        cov, pre = wall_scores(xyz, sub, floor, ceiling)
        f1 = 0.0 if cov + pre <= 0 else 2 * cov * pre / (cov + pre)
        d = "" if prev is None else f"  (+{cov - prev:.3f})"
        prev = cov
        print(f"  {name:16s} {len(sub):7d} {cov:10.3f} {pre:9.3f} {f1:7.3f}{d}")

    n_short = int((lens < 4000).sum())
    print(f"\n  Lyhyita (alle 4 m) on {n_short} / {len(walls)} seinaa "
          f"({n_short/len(walls)*100:.0f} %).")
    print("  Jos kattavuus nousee niista alle 0.05, mittari ei voi ohjata")
    print("  lyhyiden seinien korjaamista eika matriisi voi sita palkita.")


if __name__ == "__main__":
    main(*sys.argv[1:])

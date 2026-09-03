"""Mika saanto erottaa seinan roskasta, kun KORKEUS ei sita tee?

`wall_normals._segments` vaatii etta segmentin z-vali kattaa 45 % kaistasta:

    need_span = _SPAN_FRAC * (z_hi - z_lo)
    if pz.max() - pz.min() < need_span: continue

Mitattu (`_normals_gate_probe.py`): tama on detektorin SITOVA portti, ja sen
loysaaminen 0.45 -> 0.20 nosti scene_07002:ssa kattavuuden 0.222 -> 0.800 ja
tarkkuuden 0.500 -> 0.633. Molemmat paranivat, joten portti ei erotellut
seinaa roskasta — se karsi seinia.

Syy on sama kuin histogrammissa: TASO, EI SUHDE. `z_hi - z_lo` on koko
rakennuksen kaista. Rohbau on 10 m runkohalli, jossa valiseinat ovat 2-4 m
korkeita eivatka yllakaan kattoon — vaatimus "45 % kaistasta" on niille
mahdoton riippumatta siita ovatko ne oikeita seinia.

Portilla on silti tyo: ilman mitaan porttia hyllyn reuna ja putki ovat
pystypintoja siina missa seinakin. Etsitaan KOLMAS MITATTAVA ERO korkeuden
sijaan. Ehdokas: seina SEISOO LATTIALLA, roska leijuu.

Saannot ajetaan detektorin ytimessa GT:ta vastaan pituusluokittain. Pelkka
kattavuus ei riita — tarkkuus on vieressa, koska loysaaminen tuo roskaa.

Kaytto: _normals_span_rule.py <scene_dir> [scene_dir ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from _normals_gate_probe import _score  # noqa: E402

_STRUCT = (5, 6, 8, 15)
_MIN_PTS_GT = 2000


def _rules():
    """(nimi, fn(L, pz, z_lo, z_hi) -> bool kelpaako segmentti).

    `L` on segmentin pituus. Se on mukana koska paras testattu saanto
    (`span 0.20`) on yha osuus RAKENNUKSEN kaistasta — sama vikaluokka jota
    ollaan korjaamassa, vain lievempi. Aspektisaanto vertaa segmenttia
    ITSEENSA: seina on korkea suhteessa omaan pituuteensa, hyllynreuna ei.

    Kaistalla katkaisu on silti tarpeen: 30 m perimetriseinaa ei saa vaatia
    30 m korkeaksi. Siksi `min(L, kaista)`.
    """
    def span(frac):
        return lambda L, pz, lo, hi: (pz.max() - pz.min()) >= frac * (hi - lo)

    def katto(mm, frac=0.45):
        """`min(mm, frac*kaista)` — fysikaalinen minimikorkeus, KATKAISTUNA
        nykyiseen porttiin.

        Matalassa tilassa `frac*kaista` on pienempi ja saanto on TASMALLEEN
        nykyinen (kellari: kaista 1075 mm -> 484 mm). Korkeassa hallissa
        katkaisu puree ja vaatimus lakkaa kasvamasta katonkorkeuden mukana.
        Nain saanto ei voi olla nykyista TIUKEMPI missaan.

        Korkeus millimetreina on rakennuksen ominaisuus eika skannin: se ei
        riipu pistetiheydesta kuten kielletyt pistekynnykset.
        """
        return lambda L, pz, lo, hi: (pz.max() - pz.min()) >= min(mm, frac * (hi - lo))

    return [
        ("span 0.45 (nyky)", span(0.45)),
        ("span 0.20", span(0.20)),
        ("katko 2400", katto(2400.0)),
        ("katko 2600", katto(2600.0)),
        ("katko 2800", katto(2800.0)),
        ("katko 3000", katto(3000.0)),
        ("katko 3400", katto(3400.0)),
    ]


def _patched_segments(rule):
    from scan2bim.core.segmentation import wall_normals as WN

    def _segments(q, sel, deg, z_lo, z_hi):
        n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
        u = np.array([-n[1], n[0]])
        xy, z = q[sel][:, :2], q[sel][:, 2]
        off = xy @ n
        nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
        hist, edges = np.histogram(off, bins=nb)
        centers = 0.5 * (edges[:-1] + edges[1:])
        peaks = [i for i in range(1, len(hist) - 1)
                 if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]
        out = []
        for i in peaks:
            c = float(centers[i])
            m = np.abs(off - c) < WN._PLANE_BAND
            if m.sum() < WN._MIN_PTS:
                continue
            t, zz = xy[m] @ u, z[m]
            order = np.argsort(t)
            t, zz = t[order], zz[order]
            cuts = np.flatnonzero(np.diff(t) > WN._GAP_MM) + 1
            for pt, pz in zip(np.split(t, cuts), np.split(zz, cuts)):
                if len(pt) < WN._MIN_PTS or float(pt[-1] - pt[0]) < WN._MIN_LEN:
                    continue
                if not rule(float(pt[-1] - pt[0]), pz, z_lo, z_hi):
                    continue
                out.append({"offset": c, "a": n * c + u * float(pt[0]),
                            "b": n * c + u * float(pt[-1]), "n": int(len(pt))})
        return out
    return _segments


def _load(scene: Path):
    xyz = np.load(scene / "coord.npy").astype(np.float64)
    cls = np.load(scene / "class.npy").ravel()
    inst = np.load(scene / "instance.npy").ravel()
    if np.ptp(xyz[:, 0]) < 500.0:
        xyz = xyz * 1000.0
    gt, glen = [], []
    struct = np.isin(cls, _STRUCT)
    for i in np.unique(inst[struct]):
        sel = struct & (inst == i)
        if sel.sum() < _MIN_PTS_GT:
            continue
        p = xyz[sel]
        gt.append(p[:, :2])
        d = p[:, :2] - p[:, :2].mean(axis=0)
        _, vec = np.linalg.eigh(np.cov(d.T))
        glen.append(float(np.ptp(d @ vec[:, -1])))
    return xyz, gt, np.array(glen)


def main(*scene_dirs: str) -> None:
    import open3d as o3d

    from scan2bim.core.segmentation import wall_normals as WN

    orig = WN._segments
    totals: dict[str, list] = {}
    try:
        for sd in scene_dirs:
            scene = Path(sd)
            xyz, gt, glen = _load(scene)
            pc = o3d.geometry.PointCloud()
            pc.points = o3d.utility.Vector3dVector(xyz)
            del xyz
            print(f"\n{scene.name}: {len(gt)} GT-instanssia "
                  f"(1-2 m: {int(((glen>=1000)&(glen<2000)).sum())}, "
                  f"2-4 m: {int(((glen>=2000)&(glen<4000)).sum())}, "
                  f"yli 4 m: {int((glen>=4000).sum())})")
            print(f"  {'saanto':24s} {'seinia':>7s} {'kattav':>7s} {'tarkk':>7s} "
                  f"{'F1':>7s} {'2-4 m':>7s} {'1-2 m':>7s}")
            det = WN.NormalsWallDetector()
            for name, rule in _rules():
                WN._segments = _patched_segments(rule)
                try:
                    walls = det.detect(pc).walls
                except Exception as e:  # noqa: BLE001
                    print(f"  {name:24s} kaatui: {e}")
                    continue
                cov, pre, n = _score(walls, gt)
                f1 = 0.0 if cov + pre <= 0 else 2 * cov * pre / (cov + pre)
                c24, _, _ = _score(walls, [g for g, L in zip(gt, glen) if 2000 <= L < 4000])
                c12, _, _ = _score(walls, [g for g, L in zip(gt, glen) if 1000 <= L < 2000])
                totals.setdefault(name, []).append((cov, pre, f1))
                print(f"  {name:24s} {n:7d} {cov:7.3f} {pre:7.3f} {f1:7.3f} "
                      f"{c24:7.3f} {c12:7.3f}", flush=True)
    finally:
        WN._segments = orig

    if len(scene_dirs) > 1:
        print(f"\n  {'KESKIARVO':24s} {'':>7s} {'kattav':>7s} {'tarkk':>7s} {'F1':>7s}")
        for name, rows in totals.items():
            a = np.array(rows)
            print(f"  {name:24s} {'':>7s} {a[:,0].mean():7.3f} "
                  f"{a[:,1].mean():7.3f} {a[:,2].mean():7.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

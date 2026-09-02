"""Mika piikkisaanto loytaa lyhyet seinat ILMAN etta tarkkuus romahtaa?

Mitattu juurisyy: `wall_histogram._peaks_1d` kayttaa GLOBAALIA kynnysta

    thr = max(hist.mean() + 3.0 * hist.std(), 50)

ja hajonta on perimetripiikkien takia 3.5x keskiarvo. Scene_07002:n akselilla 0
kynnys on 16553 ja 1642 binista vain 10 ylittaa sen. GT-instansseista
yli 4 m ylittaa 0.86, 2-4 m 0.62 ja 1-2 m **0.00**.

Kynnyksen loysaaminen loytaa lisaa seinia mutta tuo myos roskaa. Kumpi voittaa,
sita EI saa paattaa — se on mitattava molemmilla suunnilla. Tama ajaa
detektorin ydintaa (ei koko putkea) eri saannoilla ja pisteyttaa GT:ta vasten:

  saanto            = miten kynnys lasketaan
  kattavuus (recall)= osuus GT-instansseista joilla on seina kaistan sisalla
  tarkkuus          = osuus detektoiduista seinista jotka osuvat GT-seinaan

Nopea koska putkea ei ajeta — vain detektorin `_detect_walls`.

Kaytto: _hist_rule_sweep.py <scene_dir> [voxel]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_STRUCT = (5, 6, 8, 15)
_MIN_PTS = 2000
_BAND = 300.0        # mm — kuinka lahelta seinan on kuljettava (vapaampi kuin
                     # lopullinen 80 mm, koska tassa ei ole viela pintalukitusta)
_HIT = 0.30


def _rules():
    """(nimi, funktio hist -> kynnys). Kaikki suhteita, ei absoluutteja."""
    import numpy as np

    def globaali(h):                     # nykyinen
        return max(h.mean() + 3.0 * h.std(), 50.0)

    def robusti(h, k=3.0):
        """Mediaani + k x MAD: perimetripiikit eivat paisuta mediaania."""
        nz = h[h > 0]
        if not len(nz):
            return 50.0
        med = float(np.median(nz))
        mad = float(np.median(np.abs(nz - med))) * 1.4826
        return max(med + k * mad, 50.0)

    def kvantiili(h, q=0.995):
        nz = h[h > 0]
        return max(float(np.quantile(nz, q)), 50.0) if len(nz) else 50.0

    def osuus_huipusta(h, f=0.02):
        return max(f * float(h.max()), 50.0)

    return [
        ("globaali (nyky)", globaali),
        ("robusti k=3", lambda h: robusti(h, 3.0)),
        ("robusti k=6", lambda h: robusti(h, 6.0)),
        ("robusti k=12", lambda h: robusti(h, 12.0)),
        ("kvantiili .99", lambda h: kvantiili(h, 0.99)),
        ("kvantiili .995", lambda h: kvantiili(h, 0.995)),
        ("2 % huipusta", lambda h: osuus_huipusta(h, 0.02)),
        ("5 % huipusta", lambda h: osuus_huipusta(h, 0.05)),
    ]


def _score(walls, gt):
    """(kattavuus, tarkkuus, seinia) GT-instansseja vastaan."""
    if not walls:
        return 0.0, 0.0, 0
    segs = []
    for w in walls:
        a = np.asarray(w.axis[0], float)[:2]
        b = np.asarray(w.axis[1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        segs.append((a, (b - a) / L, L))
    if not segs:
        return 0.0, 0.0, 0
    found = 0
    used = np.zeros(len(segs), dtype=bool)
    for xy in gt:
        hit = np.zeros(len(xy), dtype=bool)
        for si, (a, u, L) in enumerate(segs):
            d = xy - a
            s = d @ u
            t = d @ np.array([-u[1], u[0]])
            m = (s > -_BAND) & (s < L + _BAND) & (np.abs(t) < _BAND)
            if m.any():
                hit |= m
                if m.mean() > 0.05:
                    used[si] = True
        found += bool(hit.mean() >= _HIT)
    return found / len(gt), float(used.mean()), len(segs)


def main(scene_dir: str, voxel: str = "21.8") -> None:
    import open3d as o3d

    from scan2bim.core.segmentation import wall_histogram as WH

    scene = Path(scene_dir)
    xyz = np.load(scene / "coord.npy").astype(np.float64)
    cls = np.load(scene / "class.npy").ravel()
    inst = np.load(scene / "instance.npy").ravel()
    if np.ptp(xyz[:, 0]) < 500.0:
        xyz = xyz * 1000.0

    gt, glen = [], []
    struct = np.isin(cls, _STRUCT)
    for i in np.unique(inst[struct]):
        sel = struct & (inst == i)
        if sel.sum() < _MIN_PTS:
            continue
        p = xyz[sel]
        gt.append(p[:, :2])
        d = p[:, :2] - p[:, :2].mean(axis=0)
        _, vec = np.linalg.eigh(np.cov(d.T))
        glen.append(float((d @ vec[:, -1]).ptp()))
    glen = np.array(glen)

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(xyz)
    pc = pc.voxel_down_sample(float(voxel))
    pts = np.asarray(pc.points)
    del pc, xyz
    z = pts[:, 2]
    z0, h = float(z.min()), float(z.max() - z.min())
    mid = pts[(z > z0 + WH._MID_LO * h) & (z < z0 + WH._MID_HI * h)]

    det = WH.WallDetectorHistogram()
    orig = WH._peaks_1d
    print(f"{scene.name}: {len(gt)} GT-instanssia "
          f"(1-2 m: {int(((glen>=1000)&(glen<2000)).sum())}, "
          f"2-4 m: {int(((glen>=2000)&(glen<4000)).sum())}, "
          f"yli 4 m: {int((glen>=4000).sum())})")
    print(f"  {'saanto':18s} {'seinia':>7s} {'kattav':>7s} {'tarkk':>7s} "
          f"{'2-4 m':>7s} {'1-2 m':>7s}")
    for name, fn in _rules():
        def patched(coord, lo, hi, _fn=fn):
            nb = int((hi - lo) / WH._BIN) + 1
            if nb < 1:
                return []
            hist, edges = np.histogram(coord, bins=nb, range=(lo, hi))
            thr = _fn(hist)
            over = hist >= thr
            out, i = [], 0
            while i < nb:
                if over[i]:
                    j = i
                    while j < nb and over[j]:
                        j += 1
                    out.append(((edges[i] + edges[j]) / 2.0, int(hist[i:j].sum())))
                    i = j
                else:
                    i += 1
            return out

        WH._peaks_1d = patched
        try:
            walls = det._detect_walls(mid[:, :2], z0, h)
        except Exception as e:  # noqa: BLE001
            print(f"  {name:18s} kaatui: {e}")
            continue
        cov, pre, n = _score(walls, gt)
        c24, _, _ = _score(walls, [g for g, L in zip(gt, glen) if 2000 <= L < 4000])
        c12, _, _ = _score(walls, [g for g, L in zip(gt, glen) if 1000 <= L < 2000])
        print(f"  {name:18s} {n:7d} {cov:7.3f} {pre:7.3f} {c24:7.3f} {c12:7.3f}")
    WH._peaks_1d = orig


if __name__ == "__main__":
    main(*sys.argv[1:])

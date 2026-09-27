"""Onko `wall_normals`issa sama PITUUSVINOUMA kuin histogrammissa — ja jos ei,
mika sen porteista maksaa kattavuutta?

Histogrammin juurisyy oli GLOBAALI kynnys (`mean + 3*std`), joka sulki lyhyet
seinat ulos rakenteellisesti. `wall_normals._segments` valitsee tasot toisin:

    peaks = [i for i in ... if hist[i] and hist[i] == hist[i-2:i+3].max()]

Se on PAIKALLINEN maksimi ilman kynnysta, joten pitka seina ei voi nostaa
rimaa lyhyen ulottumattomiin. Sita EI kuitenkaan saa paattaa lukemalla —
tama mittaa sen GT:ta vastaan pituusluokittain.

Loput portit ovat absoluutteja, ja juuri niita projektin saanto kieltaa
("mikaan absoluuttinen pistekynnys ei saa maarata tulosta"):

    _MIN_PTS   = 60      pisteita tasokaistassa JA segmentissa
    _MIN_LEN   = 900 mm  segmentin pituus
    _SPAN_FRAC = 0.45    segmentin z-valin osuus kaistasta
    _GAP_MM    = 700 mm  tata pidempi aukko katkaisee segmentin

Ablaatio: jokainen portti loysataan VUOROLLAAN yksin, muut ennallaan. Nain
nakyy kumpi niista on sitova eika vain lasna. Kattavuuden nousu yksin ei
riita — tarkkuus tulostetaan viereen, koska loysaaminen tuo aina roskaa.

Kaytto: _normals_gate_probe.py <scene_dir> [voxel]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_STRUCT = (5, 6, 8, 15)
_MIN_PTS_GT = 2000
_BAND = 300.0
_HIT = 0.30


def _score(walls, gt):
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


def main(scene_dir: str) -> None:
    import open3d as o3d

    from ordinate.core.segmentation import wall_normals as WN

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
        if sel.sum() < _MIN_PTS_GT:
            continue
        p = xyz[sel]
        gt.append(p[:, :2])
        d = p[:, :2] - p[:, :2].mean(axis=0)
        _, vec = np.linalg.eigh(np.cov(d.T))
        glen.append(float(np.ptp(d @ vec[:, -1])))
    glen = np.array(glen)

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(xyz)
    del xyz

    keep = dict(_MIN_PTS=WN._MIN_PTS, _MIN_LEN=WN._MIN_LEN,
                _SPAN_FRAC=WN._SPAN_FRAC, _GAP_MM=WN._GAP_MM)
    variants = [("nykyinen", {})]
    variants += [(f"{k} {keep[k]} -> {v}", {k: v}) for k, v in
                 (("_MIN_PTS", 15), ("_MIN_LEN", 400.0),
                  ("_SPAN_FRAC", 0.20), ("_GAP_MM", 1500.0))]
    variants += [("kaikki loysalla", {"_MIN_PTS": 15, "_MIN_LEN": 400.0,
                                      "_SPAN_FRAC": 0.20, "_GAP_MM": 1500.0})]

    n12 = int(((glen >= 1000) & (glen < 2000)).sum())
    n24 = int(((glen >= 2000) & (glen < 4000)).sum())
    n4 = int((glen >= 4000).sum())
    print(f"{scene.name}: {len(gt)} GT-instanssia "
          f"(1-2 m: {n12}, 2-4 m: {n24}, yli 4 m: {n4})")
    print(f"  {'variantti':24s} {'seinia':>7s} {'kattav':>7s} {'tarkk':>7s} "
          f"{'yli 4m':>7s} {'2-4 m':>7s} {'1-2 m':>7s}")

    det = WN.NormalsWallDetector()
    for name, over in variants:
        for k, v in over.items():
            setattr(WN, k, v)
        try:
            walls = det.detect(pc).walls
        except Exception as e:  # noqa: BLE001
            print(f"  {name:24s} kaatui: {e}")
            walls = []
        finally:
            for k, v in keep.items():
                setattr(WN, k, v)
        cov, pre, n = _score(walls, gt)
        c4, _, _ = _score(walls, [g for g, L in zip(gt, glen) if L >= 4000])
        c24, _, _ = _score(walls, [g for g, L in zip(gt, glen) if 2000 <= L < 4000])
        c12, _, _ = _score(walls, [g for g, L in zip(gt, glen) if 1000 <= L < 2000])
        print(f"  {name:24s} {n:7d} {cov:7.3f} {pre:7.3f} "
              f"{c4:7.3f} {c24:7.3f} {c12:7.3f}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])

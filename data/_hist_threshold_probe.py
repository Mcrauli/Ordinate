"""Jaako lyhyt valiseina histogrammidetektorin GLOBAALIN kynnyksen alle?

`wall_histogram._peaks_1d` valitsee seinapiikit nain:

    thr = max(hist.mean() + 3.0 * hist.std(), 50)

Se on YKSI kynnys koko rakennuksen akselille. Binin pistemaara on suoraan
verrannollinen seinan PITUUTEEN, joten 30 m perimetriseina tuottaa binia
kohti moninkertaisesti sen mita 3 m valiseina — ja samat jattipiikit
paisuttavat `std()`:n, joka nostaa kynnyksen entisestaan. Taso, ei suhde.

Ennuste jos tama on syy: mitattuna GT:n seinainstanssien kohdalla lyhyiden
seinien binimaara on juuri ja juuri kynnyksen ALLA, ja pitkien selvasti yli.

Tama laskee saman histogrammin kuin detektori ja kertoo jokaisesta GT-
instanssista, ylittaako sen kohta kynnyksen. Verrataan pituusluokittain.

Kaytto: _hist_threshold_probe.py <scene_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_STRUCT = (5, 6, 8, 15)
_MIN_PTS = 2000


def main(scene_dir: str, voxel: str = "21.8") -> None:
    import open3d as o3d

    from scan2bim.core.segmentation.wall_histogram import (
        _BIN, _MID_HI, _MID_LO, _PEAK_MIN_PTS, _dominant_angle,
    )

    scene = Path(scene_dir)
    xyz = np.load(scene / "coord.npy").astype(np.float64)
    cls = np.load(scene / "class.npy").ravel()
    inst = np.load(scene / "instance.npy").ravel()
    if np.ptp(xyz[:, 0]) < 500.0:
        xyz = xyz * 1000.0

    # Sama tyopilvi kuin detektorilla: auto-voxel + keskikorkeusviipale.
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(xyz)
    pc = pc.voxel_down_sample(float(voxel))
    pts = np.asarray(pc.points)
    del pc
    z = pts[:, 2]
    z0 = float(z.min())
    h = float(z.max() - z0)
    mid = pts[(z > z0 + _MID_LO * h) & (z < z0 + _MID_HI * h)]
    print(f"{scene.name}: tyopilvi {len(pts):,}, keskiviipale {len(mid):,} "
          f"(z {z0 + _MID_LO*h:.0f}..{z0 + _MID_HI*h:.0f} mm)")

    xy = mid[:, :2]
    theta = _dominant_angle(xy)
    c, s = np.cos(-theta), np.sin(-theta)
    rot = xy @ np.array([[c, -s], [s, c]]).T
    lo, hi = rot.min(axis=0), rot.max(axis=0)

    hists = []
    for a in (0, 1):
        nb = int((hi[a] - lo[a]) / _BIN) + 1
        hist, edges = np.histogram(rot[:, a], bins=nb, range=(lo[a], hi[a]))
        # VANHA saanto tarkoituksella: tama koetin dokumentoi mika oli vikana.
        thr = max(hist.mean() + 3.0 * hist.std(), float(_PEAK_MIN_PTS))
        hists.append((hist, edges, thr))
        print(f"  akseli {a}: {nb} binia, keskiarvo {hist.mean():.0f}, "
              f"hajonta {hist.std():.0f}, KYNNYS {thr:.0f}, "
              f"yli kynnyksen {int((hist >= thr).sum())} binia, "
              f"suurin bini {int(hist.max())}")

    struct = np.isin(cls, _STRUCT)
    rows = []
    for i in np.unique(inst[struct]):
        sel = struct & (inst == i)
        if sel.sum() < _MIN_PTS:
            continue
        p = xyz[sel]
        q = p[:, :2] @ np.array([[c, -s], [s, c]]).T
        cen = q.mean(axis=0)
        d = q - cen
        ev, vec = np.linalg.eigh(np.cov(d.T))
        length = float((d @ vec[:, -1]).ptp())
        # Kumpi akseli on seinan NORMAALI (se jolla piikki on)?
        n = vec[:, 0]
        a = 0 if abs(n[0]) >= abs(n[1]) else 1
        hist, edges, thr = hists[a]
        k = int(np.clip(np.searchsorted(edges, cen[a]) - 1, 0, len(hist) - 1))
        peak = int(hist[max(0, k - 1):k + 2].max())
        rows.append((length, peak, thr, peak >= thr))

    if not rows:
        print("ei instansseja")
        return
    L = np.array([r[0] for r in rows])
    P = np.array([r[1] for r in rows])
    T = np.array([r[2] for r in rows])
    OK = np.array([r[3] for r in rows])
    print(f"\n  {'pituusluokka':14s} {'n':>3s} {'binimaara med':>14s} "
          f"{'kynnys':>8s} {'yli kynnyksen':>14s}")
    for name, sel in (("1-2 m", (L >= 1000) & (L < 2000)),
                      ("2-4 m", (L >= 2000) & (L < 4000)),
                      ("yli 4 m", L >= 4000)):
        if not sel.any():
            continue
        print(f"  {name:14s} {int(sel.sum()):3d} {np.median(P[sel]):14.0f} "
              f"{np.median(T[sel]):8.0f} {OK[sel].mean():13.2f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

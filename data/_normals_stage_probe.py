"""Missa kohtaa normals-detektori pudottaa GT-seinan?

Jalanjaljen sisalla on kahdeksan tasomaista 2.3-3.3 m seinaa jotka EI YKSIKAAN
detektori loyda (`_missing_who_finds.py`). Pystymaski nakee ne, joten haviö on
maskin jalkeen. Tama ajaa normals-detektorin vaiheet yksi kerrallaan ja kertoo
per GT-instanssi kuinka suuri osa sen pisteista selviaa kustakin portista.
Vastaus on portin nimi, ei arvaus.

Rohbaun cloud.ply ja coord.npy vastaavat toisiaan pisteittain, joten
instanssileima seuraa pistetta koko ketjun lapi (voxeloinnin jalkeen
lahimman naapurin kautta).

Kaytto: _normals_stage_probe.py <scene_dir> [inst,inst,...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from ordinate.core.segmentation import wall_normals as WN

FACE = {5, 6, 8, 15}
MIN_PTS = 2000

STAGES = ["kaikki", "kaista", "pysty", "suunta", "taso", "segmentti", "span", "pari"]


def main() -> None:
    scene = Path(sys.argv[1])
    want = {int(x) for x in sys.argv[2].split(",")} if len(sys.argv) > 2 else None

    G = np.load(scene / "coord.npy").astype(np.float64)
    if float(np.ptp(G[:, 0])) < 500.0:
        G = G * 1000.0
    C = np.load(scene / "class.npy")
    I = np.load(scene / "instance.npy")

    insts = []
    for k in np.unique(I):
        m = I == k
        if m.sum() < MIN_PTS or not np.isin(C[m], list(FACE)).any():
            continue
        if want is not None and int(k) not in want:
            continue
        insts.append(int(k))
    print(f"{scene.name}: {len(insts)} instanssia tutkittavana")

    q, nrm = WN._prepare(G)
    tree = cKDTree(G)
    _, idx = tree.query(q, k=1, workers=-1)
    qi = I[idx]
    print(f"  voxeloitu {len(G):,} -> {len(q):,}")

    surv = {k: {} for k in insts}

    def mark(stage: str, mask: np.ndarray) -> None:
        lab = qi[mask]
        for k in insts:
            surv[k][stage] = max(surv[k].get(stage, 0), int((lab == k).sum()))

    base = np.ones(len(q), bool)
    mark("kaikki", base)

    floor = float(np.percentile(q[:, 2], 2))
    ceiling = float(np.percentile(q[:, 2], 98))
    z_lo, z_hi = floor + WN._BAND_LO, ceiling - WN._BAND_HI
    band = (q[:, 2] > z_lo) & (q[:, 2] < z_hi)
    mark("kaista", band)

    ang = np.degrees(np.arctan2(nrm[:, 1], nrm[:, 0])) % 180.0
    vert = band & (np.abs(nrm[:, 2]) < WN._VERT_NZ)
    mark("pysty", vert)

    need_span = WN._need_span(z_lo, z_hi)
    print(f"  kaista {z_lo:.0f}..{z_hi:.0f} mm, need_span {need_span:.0f} mm")

    dirs = WN._directions(ang[vert])
    print(f"  suuntia {len(dirs)}")

    for deg in dirs:
        d = np.abs((ang - deg + 90.0) % 180.0 - 90.0)
        sel = vert & (d < WN._DIR_TOL_DEG)
        if sel.sum() < WN._MIN_PTS:
            continue
        mark("suunta", sel)

        gi = np.flatnonzero(sel)
        n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
        u = np.array([-n[1], n[0]])
        xy, z = q[sel][:, :2], q[sel][:, 2]
        off = xy @ n
        nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
        hist, edges = np.histogram(off, bins=nb)
        centers = 0.5 * (edges[:-1] + edges[1:])
        peaks = [i for i in range(1, len(hist) - 1)
                 if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

        segs = []
        for i in peaks:
            c = float(centers[i])
            m = np.abs(off - c) < WN._PLANE_BAND
            if m.sum() < WN._MIN_PTS:
                continue
            full = np.zeros(len(q), bool)
            full[gi[m]] = True
            mark("taso", full)

            t, zz = xy[m] @ u, z[m]
            src = gi[m]
            order = np.argsort(t)
            t, zz, src = t[order], zz[order], src[order]
            cuts = np.flatnonzero(np.diff(t) > WN._GAP_MM) + 1
            for pt, pz, ps in zip(np.split(t, cuts), np.split(zz, cuts),
                                  np.split(src, cuts)):
                if len(pt) < WN._MIN_PTS or float(pt[-1] - pt[0]) < WN._MIN_LEN:
                    continue
                full = np.zeros(len(q), bool)
                full[ps] = True
                mark("segmentti", full)
                if float(pz.max() - pz.min()) < need_span:
                    continue
                mark("span", full)
                segs.append({"offset": c, "a": n * c + u * float(pt[0]),
                             "b": n * c + u * float(pt[-1]), "n": int(len(pt)),
                             "src": ps})

        for w in WN._pair_faces([dict(s) for s in segs], deg):
            keep = np.zeros(len(q), bool)
            t0, t1 = w["t0"], w["t1"]
            for s in segs:
                st = q[s["src"]][:, :2] @ u
                keep[s["src"][(st >= t0) & (st <= t1)]] = True
            mark("pari", keep)

    print(f"  {'inst':>6} {'pisteita':>9} " + " ".join(f"{s:>9}" for s in STAGES[1:]))
    for k in insts:
        tot = surv[k].get("kaikki", 0)
        if tot == 0:
            print(f"  {k:>6} {0:>9}  (ei voxelipisteita)")
            continue
        cells = " ".join(f"{surv[k].get(s, 0) / tot:>9.2f}" for s in STAGES[1:])
        print(f"  {k:>6} {tot:>9,} {cells}")


if __name__ == "__main__":
    main()

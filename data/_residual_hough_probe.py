"""Loytaako viivahaku (HoughLinesP) tall-soluista ne seinat jotka hajoavat
komponenteiksi? Tuotannon syotepilvi (`_residual_cloud_dump.py`).
Kaytto: _residual_hough_probe.py <dump_dir> <k> <model.json> <wallish.npz>"""
import json
import sys

import cv2
import numpy as np

sys.path.insert(0, "data")
from _missing_line_probe import lines


def main(dump, k, mj, npz):
    import ordinate.core.semantics.residual_walls as RW
    from ordinate.schemas.model import Wall
    z = np.load(f"{dump}/residual_in_{k}.npz")
    pts = z["pts"].astype(float); fz, cz = float(z["fz"]), float(z["cz"])
    walls = [Wall(**w) for w in json.load(open(f"{dump}/residual_walls_{k}.json", encoding="utf-8"))]
    h = cz - fz
    z_lo = fz + min(RW._WAIST_LO_FRAC * h, RW._WAIST_LO_MM); z_hi = fz + RW._WAIST_HI * h
    band = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
    free = band[~RW._claimed(band, walls)]
    o = free[:, :2].min(0)
    ij = np.floor((free[:, :2] - o) / RW._CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    flat = ij[:, 0] * ny + ij[:, 1]
    counts = np.bincount(flat, minlength=nx * ny)
    need = max(RW._SURF_FRAC * float(np.median(counts[counts > 0])), 2.0)
    tall = RW._tall_cells(free[:, 2], flat, nx * ny, min(RW._MIN_VSPAN_MM, RW._CELL_VSPAN_FRAC * (z_hi - z_lo)))
    mask = ((counts >= need) & tall).reshape(nx, ny).astype(np.uint8) * 255
    segs = cv2.HoughLinesP(mask, 1, np.pi / 360, threshold=10, minLineLength=15, maxLineGap=6)
    segs = [] if segs is None else segs[:, 0, :]
    S = [(o + np.array([b, a]) * RW._CELL + 50, o + np.array([d, c]) * RW._CELL + 50) for a, b, c, d in segs]
    Ls = [np.linalg.norm(q - p) for p, q in S]
    print(f"tall-pintasoluja {int((mask > 0).sum())}, viivoja {len(S)}, yhteensa {sum(Ls)/1000:.1f} m")
    zc = np.load(npz); W = zc["q"][zc["m"]].astype(float)[:, :2]

    def cover(P, segs_):
        hit = np.zeros(len(P), bool)
        for p, q in segs_:
            d = q - p; L = np.linalg.norm(d)
            if L < 1: continue
            u = d / L; n = np.array([-u[1], u[0]]); t = (P - p) @ u
            hit |= (t > -150) & (t < L + 150) & (np.abs((P - p) @ n) < 150)
        return hit.mean()
    tot = got = 0.0
    for r in lines(mj, npz, 1500.0):
        if r[2] > 20: continue
        c = cover(r[6][:, :2], S); tot += r[0]; got += r[0] * c
    print(f"puuttuvista tasomaisista linjoista katettu {got/1000:.1f} / {tot/1000:.1f} m")
    sup = []
    for (p, q), L in zip(S, Ls):
        d = q - p; u = d / L; n = np.array([-u[1], u[0]]); t = (W - p) @ u
        s = (t > 0) & (t < L) & (np.abs((W - p) @ n) < 100)
        sup.append(np.unique(np.floor(t[s] / 250)).size / max(1, int(L // 250)))
    sup = np.array(sup); Ls = np.array(Ls)
    print(f"viivojen seinapinta (wallish-kate): mediaani {np.median(sup):.2f}; alle 0.3: {Ls[sup < 0.3].sum()/1000:.1f} m / {Ls.sum()/1000:.1f} m")


if __name__ == "__main__":
    main(*sys.argv[1:])

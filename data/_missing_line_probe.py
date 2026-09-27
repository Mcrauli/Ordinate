"""Lunastamattomat seinamaiset LINJAT ja miksi ne puuttuvat (GT-vapaa).

Kaytto: _missing_line_probe.py <model.json> <wallish.npz> [min_len_mm]
Tulostaa jokaiselle >= min_len linjalle: pituus, lahin samansuuntainen mallin
seina (etaisyys, kulma), kaistan tasomaisuus (MAD) ja pystyulottuvuus.
"""
import json
import sys

import numpy as np
from scipy.ndimage import label

sys.path.insert(0, "data")
from _cov_gap_nogt import explained


def lines(mj, npz, min_len=1500.0):
    min_len = float(min_len)
    m = json.load(open(mj, encoding="utf-8"))
    z = np.load(npz)
    q = z["q"].astype(float); wm = z["m"]
    fz, cz = float(z["fz"]), float(z["cz"])
    W = q[wm]
    free = W[~explained(W[:, :2], m["walls"], 60.0)]
    cell = 100.0
    o = free[:, :2].min(0)
    ij = np.floor((free[:, :2] - o) / cell).astype(int)
    nx, ny = ij.max(0) + 1
    occ = np.zeros((nx, ny), bool); occ[ij[:, 0], ij[:, 1]] = True
    lab, n = label(occ, np.ones((3, 3), int))
    pl = lab[ij[:, 0], ij[:, 1]]
    walls = [(np.array(w["axis"][0], float), np.array(w["axis"][1], float), w) for w in m["walls"]]
    rows = []
    for k in range(1, n + 1):
        P = free[pl == k]
        if len(P) < 50:
            continue
        c = P[:, :2].mean(0); A = P[:, :2] - c
        ev, V = np.linalg.eigh(A.T @ A / len(A))
        u, nn = V[:, 1], V[:, 0]
        s = A @ u; L = float(np.ptp(s)); wdt = float(np.ptp(A @ nn))
        if L < min_len or L / max(wdt, 1.0) < 4:
            continue
        mad = float(np.median(np.abs(A @ nn - np.median(A @ nn))))
        vspan = float(np.percentile(P[:, 2], 95) - np.percentile(P[:, 2], 5))
        best = (1e9, 90.0, "")
        for a, b, w in walls:
            d = b - a; Lw = np.linalg.norm(d)
            if Lw < 1: continue
            uw = d / Lw
            ang = np.degrees(np.arccos(min(1.0, abs(float(u @ uw)))))
            if ang > 15: continue
            t = np.clip((c - a) @ uw, 0, Lw)
            dist = float(np.linalg.norm(c - (a + t * uw)))
            if dist < best[0]: best = (dist, ang, w["id"])
        rows.append((L, wdt, mad, vspan, best, c, P))
    rows.sort(key=lambda r: -r[0])
    return rows


def main(mj, npz, min_len=1500.0):
    rows = lines(mj, npz, min_len)
    tot = sum(r[0] for r in rows)
    print(f"linjoja {len(rows)}  yhteensa {tot/1000:.1f} m")
    near = sum(r[0] for r in rows if r[4][0] <= 600)
    print(f"  <=600 mm samansuuntaisesta seinasta (_NEAR_EXISTING pudottaa): {near/1000:.1f} m")
    flat = sum(r[0] for r in rows if r[2] <= 20)
    print(f"  tasomaisia (MAD <= 20 mm): {flat/1000:.1f} m")
    for L, wdt, mad, vs, (d, ang, wid), c, _ in rows[:40]:
        print(f"  L={L:6.0f} lev={wdt:4.0f} MAD={mad:5.1f} pysty={vs:5.0f}  lahin={wid:14s} {d:6.0f} mm {ang:4.1f}°  @ {c[0]:.0f},{c[1]:.0f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

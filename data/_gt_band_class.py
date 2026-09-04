"""Mita mallin seinan kaistassa OIKEASTI on — labeloitu totuus per seina.

`_evidence_gt.py` tekee saman mutta on kiinnitetty Rohbau scene_07000:een.
Tama ottaa mallin, GT:n ja pilven argumentteina, jotta sita voi ajaa myos
osittain labeloidulla aineistolla: labeloimaton piste ei ole todiste
kumpaankaan suuntaan, joten se lasketaan omaan sarakkeeseensa eika
nimittajaan.

Kaista mitataan VYOTAROLTA (30-70 % korkeudesta) samoin kuin tuki ja
jatkuvuus — koko korkeudelta mitattuna lattia ja katto tayttavat jokaisen
kaistan ja luku on sama kaikille.

Kaytto: _gt_band_class.py <model.json> <coord.npy> <class.npy> [pilvi.ply]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_REG = {0: "None", 1: "Ceiling", 4: "Floor", 5: "Wall", 6: "Drywall",
        9: "Beam", 10: "Column", 13: "Window", 14: "Door", 17: "TGA/putki"}
_WAIST_LO, _WAIST_HI = 0.30, 0.70
_MARGIN = 100.0


def _band_mask(pts: np.ndarray, w: dict) -> np.ndarray:
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][1], float)[:2]
    ab = b - a
    L = float(np.linalg.norm(ab))
    if L < 1.0:
        return np.zeros(len(pts), bool)
    u = ab / L
    n = np.array([-u[1], u[0]])
    d = pts[:, :2] - a
    t = d @ u
    off = np.abs(d @ n)
    half = 0.5 * float(w.get("thickness") or 200.0) + _MARGIN
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    m = (t >= 0) & (t <= L) & (off <= half)
    if h > 0:
        m &= (pts[:, 2] >= z0 + _WAIST_LO * h) & (pts[:, 2] <= z0 + _WAIST_HI * h)
    return m


def main(model_json: str, coord_npy: str, class_npy: str,
         cloud: str | None = None) -> None:
    walls = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    G = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy)
    allp = None
    if cloud:
        import open3d as o3d
        allp = np.asarray(o3d.io.read_point_cloud(cloud).points)

    lo, hi = G.min(axis=0), G.max(axis=0)
    print(f"GT {len(G):,} pistetta, luokat "
          f"{ {_REG.get(int(k), int(k)): int(v) for k, v in zip(*np.unique(C, return_counts=True))} }")
    print(f"GT-alue x {lo[0]/1000:.0f}..{hi[0]/1000:.0f} m, "
          f"y {lo[1]/1000:.0f}..{hi[1]/1000:.0f} m")

    rows = []
    for w in walls:
        m = _band_mask(G, w)
        n = int(m.sum())
        if n == 0:
            continue
        tot = int(_band_mask(allp, w).sum()) if allp is not None else None
        cnt = {}
        for k, v in zip(*np.unique(C[m], return_counts=True)):
            cnt[_REG.get(int(k), str(int(k)))] = int(v)
        rows.append((w["id"], float(np.linalg.norm(
            np.asarray(w["axis"][1], float)[:2] - np.asarray(w["axis"][0], float)[:2])),
            n, tot, cnt))

    if not rows:
        print("\nYksikaan mallin seina ei osu labeloituun alueeseen.")
        return
    rows.sort(key=lambda r: -(r[2] / r[3] if r[3] else r[2]))
    print(f"\n{len(rows)} seinaa osuu labeloituun alueeseen "
          f"(mallissa {len(walls)})\n")
    hdr = f"{'seina':16s} {'pituus m':>8s} {'kaista':>8s} {'labeloitu':>9s} {'osuus':>6s}  luokat"
    print(hdr)
    for wid, L, n, tot, cnt in rows:
        frac = f"{n/tot:6.2f}" if tot else "     -"
        print(f"{wid:16s} {L/1000:8.1f} {tot if tot else 0:8d} {n:9d} {frac}  {cnt}")


if __name__ == "__main__":
    main(*sys.argv[1:])

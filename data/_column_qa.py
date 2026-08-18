"""Pilarien GT-vertailu: mallin pilarit vs Rohbau3D per-piste luokka 10 = Column.

Sama mittaus kuin `_beam_qa.py` palkeille. Ilman tata pilaridetektorin
kynnyksia ei ole mitattu mitaan vasten - vain silmamaaraisesti kuvista.

TARKKUUS  : mallin pilarilaatikon sisalla olevien pisteiden GT-luokka.
KATTAVUUS : kuinka moni GT:n pilari-instanssi loytyi.

Kaytto: _column_qa.py <model.json> <coord.npy> <class.npy> [instance.npy]
"""
import collections
import json
import pathlib
import sys

import numpy as np

_BAND = 100.0
_HIT = 0.05
_COL = 10
_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}


def _box(col, P):
    c = np.asarray(col["location"], float)
    pr = col["profile"]
    hw = pr["width"] / 2.0 + _BAND
    hd = pr["depth"] / 2.0 + _BAND
    d = P[:, :2] - c
    if pr["shape"] == "circle":
        inside = np.hypot(d[:, 0], d[:, 1]) <= hw
    else:
        inside = (np.abs(d[:, 0]) <= hw) & (np.abs(d[:, 1]) <= hd)
    return inside & (P[:, 2] >= col["base_z"] - _BAND) & (P[:, 2] <= col["base_z"] + col["height"] + _BAND)


def main(mj, coord_npy, class_npy, inst_npy=None):
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    if inst_npy is None:
        cand = pathlib.Path(class_npy).with_name("instance.npy")
        inst_npy = str(cand) if cand.exists() else None
    I = np.load(inst_npy).ravel() if inst_npy else None

    cols = m.get("columns", [])
    gt = C == _COL
    print(f"GT-pilaripisteita {int(gt.sum()):,} / {len(P):,}   mallin pilareita {len(cols)}")

    claimed = np.zeros(len(P), bool)
    if cols:
        print(f"\n{'pilari':12s} {'lev':>5s} {'syv':>5s} {'kork':>6s} | {'n':>8s}  GT-jakauma")
    for c in sorted(cols, key=lambda c: c["id"]):
        sel = _box(c, P)
        claimed |= sel
        tot = int(sel.sum())
        pr = c["profile"]
        head = f"{c['id']:12s} {pr['width']:5.0f} {pr['depth']:5.0f} {c['height']:6.0f} | {tot:8d}"
        if tot == 0:
            print(f"{head}  (tyhja)   <== EI EVIDENSSIA")
            continue
        cnt = collections.Counter(C[sel].tolist())
        frac = cnt.get(_COL, 0) / tot
        top = "  ".join(f"{_REG.get(k, k)}={100 * v / tot:.0f}%" for k, v in cnt.most_common(4))
        print(f"{head}  {top}" + ("   <== EI PILARIA ALLA" if frac < 0.50 else ""))

    if cols:
        prec = float((claimed & gt).sum()) / max(int(claimed.sum()), 1)
        print(f"\nTARKKUUS   mallin laatikoiden pisteista GT-pilaria: {prec:.3f}")
    print(f"KATTAVUUS  GT-pilaripisteista mallin laatikossa    : "
          f"{float((claimed & gt).sum()) / max(int(gt.sum()), 1):.3f}")

    if I is None or not gt.any():
        return
    ids, cnts = np.unique(I[gt], return_counts=True)
    hit = np.array([float((claimed[gt] & (I[gt] == i)).sum()) / c for i, c in zip(ids, cnts)])
    print(f"\n{'inst':>6s} {'n':>9s} {'lev':>6s} {'syv':>6s} {'kork':>6s} {'alaosa':>8s} {'osuus':>6s}")
    for k in np.argsort(-cnts):
        q = P[gt][I[gt] == ids[k]]
        d = q.max(0) - q.min(0)
        print(f"{ids[k]:6d} {cnts[k]:9,} {d[0]:6.0f} {d[1]:6.0f} {d[2]:6.0f} "
              f"{q[:, 2].min():8.0f} {hit[k]:6.2f}" + ("" if hit[k] >= _HIT else "   <== EI LOYDETTY"))
    found = int((hit >= _HIT).sum())
    print(f"\nINSTANSSIKATTAVUUS {found}/{len(ids)} = {found / len(ids):.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:5])

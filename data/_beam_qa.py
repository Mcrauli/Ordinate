"""Palkkien GT-vertailu: mallin palkit vs Rohbau3D per-piste luokka 9 = Beam.

Seinille on `_rohbau_qa.py`, palkeille ei ollut mitaan — joten palkkidetektorin
kynnyksia ei ole koskaan mitattu mitaan vasten. Tama tekee saman kahden suunnan
mittauksen kuin seinapuoli:

  TARKKUUS  : mallin palkkilaatikon sisalla olevien pisteiden GT-luokka.
              Jos laatikko on aidon palkin paalla, sisalla on Beam-pisteita.
  KATTAVUUS : kuinka moni GT:n palkki-instanssi (instance.npy) on jonkin mallin
              palkin loytama = paljonko aitoa palkkia jai mallintamatta.

Instanssikattavuus on tassa se merkitseva luku: yksi 27 m pitka pilarilinja on
yksi rakenne, ei 1.7 M erillista aanesta.

Kaytto: _beam_qa.py <model.json> <coord.npy> <class.npy> [instance.npy]
"""
import collections
import json
import pathlib
import sys

import numpy as np

_BAND = 100.0        # mm — laatikon marginaali joka suuntaan
_HIT = 0.05          # osuus instanssin pisteista laatikoissa -> "loydetty"
_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}
_BEAM = 9


def _box_mask(beam, P):
    """Pisteet palkin laatikossa: akselin suunta, leveys ja korkeus + _BAND."""
    a = np.array(beam["axis"][0], float)
    b = np.array(beam["axis"][1], float)
    seg = (b - a)[:2]
    L = float(np.hypot(*seg))
    if L < 1.0:
        return np.zeros(len(P), bool), 0.0
    u = seg / L
    n = np.array([-u[1], u[0]])
    d = P[:, :2] - a[:2]
    s = d @ u
    t = d @ n
    dz = P[:, 2] - 0.5 * (a[2] + b[2])
    half_w = beam["profile"]["width"] / 2.0 + _BAND
    half_h = beam["profile"]["height"] / 2.0 + _BAND
    return ((s > -_BAND) & (s < L + _BAND)
            & (np.abs(t) < half_w) & (np.abs(dz) < half_h)), L


def _pca_xy(q):
    """Instanssin OMA pituus ja leveys, ei maailman akselien mukainen laatikko.

    Vinossa oleva 27 m palkki nayttaa akselisuuntaisessa laatikossa 5 m
    levealta — se luku sai `_MAX_WIDTH`-vertailun nayttamaan silta etta GT:n
    palkit ovat leveita vaikka ne ovat vinossa.
    """
    xy = q[:, :2] - q[:, :2].mean(axis=0)
    _, V = np.linalg.eigh(xy.T @ xy / len(xy))
    proj = xy @ V[:, ::-1]
    return float(np.ptp(proj[:, 0])), float(np.ptp(proj[:, 1]))


def main(mj, coord_npy, class_npy, inst_npy=None):
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    assert len(P) == len(C), f"coord {len(P)} != class {len(C)}"
    if inst_npy is None:
        cand = pathlib.Path(class_npy).with_name("instance.npy")
        inst_npy = str(cand) if cand.exists() else None
    I = np.load(inst_npy).ravel() if inst_npy else None

    beams = m.get("beams", [])
    gt = C == _BEAM
    print(f"GT-palkkipisteita {int(gt.sum()):,} / {len(P):,}  "
          f"({100 * gt.mean():.1f} %)   mallin palkkeja {len(beams)}")
    if gt.any():
        zg = P[gt][:, 2]
        print(f"GT-palkkien z {np.percentile(zg, 2):.0f} .. {np.percentile(zg, 98):.0f}")
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=None)
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=None)
    print(f"mallin lattia {zf} katto {zc}")

    claimed = np.zeros(len(P), bool)
    if beams:
        print(f"\n{'beam':10s} {'L':>6s} {'lev':>5s} {'kork':>5s} {'z':>6s} | "
              f"{'n':>8s}  GT-jakauma laatikossa")
    for b in sorted(beams, key=lambda b: b["id"]):
        sel, L = _box_mask(b, P)
        claimed |= sel
        tot = int(sel.sum())
        pr = b["profile"]
        head = (f"{b['id']:10s} {L:6.0f} {pr['width']:5.0f} {pr['height']:5.0f} "
                f"{b['axis'][0][2]:6.0f} | {tot:8d}")
        if tot == 0:
            print(f"{head}  (tyhja)   <== EI EVIDENSSIA")
            continue
        cnt = collections.Counter(C[sel].tolist())
        frac = cnt.get(_BEAM, 0) / tot
        top = "  ".join(f"{_REG.get(k, k)}={100 * v / tot:.0f}%" for k, v in cnt.most_common(4))
        flag = "   <== EI PALKKIA ALLA" if frac < 0.50 else ""
        print(f"{head}  {top}{flag}")

    if beams:
        prec = float((claimed & gt).sum()) / max(int(claimed.sum()), 1)
        print(f"\nTARKKUUS   mallin laatikoiden pisteista GT-palkkia: {prec:.3f}")
    pt_rec = float((claimed & gt).sum()) / max(int(gt.sum()), 1)
    print(f"KATTAVUUS  GT-palkkipisteista mallin laatikossa    : {pt_rec:.3f}")

    if I is None or not gt.any():
        return
    ids, cnts = np.unique(I[gt], return_counts=True)
    hit = np.array([float((claimed[gt] & (I[gt] == i)).sum()) / c
                    for i, c in zip(ids, cnts)])
    order = np.argsort(-cnts)
    print(f"\n{'inst':>6s} {'n':>10s} {'pituus':>7s} {'lev':>6s} {'syv':>6s} "
          f"{'alapinta':>9s} {'osuus':>6s}")
    for k in order:
        q = P[gt][I[gt] == ids[k]]
        d = q.max(0) - q.min(0)
        long_xy, short_xy = _pca_xy(q)
        print(f"{ids[k]:6d} {cnts[k]:10,} {long_xy:7.0f} {short_xy:6.0f} {d[2]:6.0f} "
              f"{q[:, 2].min():9.0f} {hit[k]:6.2f}"
              + ("" if hit[k] >= _HIT else "   <== EI LOYDETTY"))
    found = int((hit >= _HIT).sum())
    print(f"\nINSTANSSIKATTAVUUS {found}/{len(ids)} = {found / len(ids):.3f}"
          f"  (kynnys {_HIT:.0%} instanssin pisteista)")


if __name__ == "__main__":
    main(*sys.argv[1:5])

"""Seinat INSTANSSEINA, ei pisteina.

`_rohbau_qa.py` mittaa kattavuuden GT-pisteista: 0.89. Se on iso luku koska
perimetriseinilla on valtaosa pisteista. Sisapuoliset valiseinat ovat pienia
pistemaaraltaan, joten ne voivat puuttua kokonaan ilman etta luku liikkuu -
sama nimittajaharha joka palkeissa piilotti 0/77:n.

Tama laskee montako GT:n seinainstanssia on mallissa: instanssi on loydetty jos
sen pisteista riittava osuus on jonkin mallin seinan kaistassa.

Kaytto: _wall_inst_qa.py <model.json> <coord.npy> <class.npy> [instance.npy]
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

_STRUCT = (5, 6, 8, 15)     # Wall, Drywall, Parapet, Facade Element
_BAND = 80.0
_HIT = 0.30                 # osuus instanssin pisteista mallin kaistassa
_MIN_PTS = 2000


def main(mj, coord_npy, class_npy, inst_npy=None):
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    if inst_npy is None:
        inst_npy = str(pathlib.Path(class_npy).with_name("instance.npy"))
    I = np.load(inst_npy).ravel()

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, cls, ins = P[band][:, :2], C[band], I[band]

    struct = np.isin(cls, _STRUCT)
    claimed = np.zeros(len(xy), bool)
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 800.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        claimed |= (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)

    ids, cnts = np.unique(ins[struct], return_counts=True)
    rows = []
    for i, n in zip(ids, cnts):
        if n < _MIN_PTS:
            continue
        sel = struct & (ins == i)
        q = xy[sel]
        ext = float(np.hypot(*(q.max(0) - q.min(0))))
        rows.append((int(i), int(n), ext, float(claimed[sel].mean())))

    rows.sort(key=lambda r: -r[1])
    print(f"{'inst':>6s} {'n':>9s} {'pituus':>7s} {'lunastettu':>10s}")
    for i, n, ext, f in rows:
        print(f"{i:6d} {n:9,} {ext:7.0f} {f:10.2f}" + ("" if f >= _HIT else "   <== EI MALLISSA"))
    # Pituusluokittain: 0.49 on eri asia jos puuttuvat ovat 0.5 m tynkia kuin
    # jos ne ovat 4 m seinia. Ilman tata luku ei kerro mita korjata.
    print("")
    print(f"{'pituusluokka':16s} {'loytyi':>7s} {'kaikki':>7s} {'osuus':>6s}")
    for lo, hi, name in ((0, 1000, "alle 1 m"), (1000, 2000, "1-2 m"),
                         (2000, 4000, "2-4 m"), (4000, 1e9, "yli 4 m")):
        grp = [r for r in rows if lo <= r[2] < hi]
        if not grp:
            continue
        ok = sum(1 for r in grp if r[3] >= _HIT)
        print(f"{name:16s} {ok:7d} {len(grp):7d} {ok / len(grp):6.2f}")

    found = sum(1 for _, _, _, f in rows if f >= _HIT)
    pt = float((claimed & struct).sum()) / max(int(struct.sum()), 1)
    print(f"\nINSTANSSIKATTAVUUS {found}/{len(rows)} = {found / max(len(rows), 1):.3f}"
          f"   (pistekattavuus {pt:.3f}, mallin seinia {len(m['walls'])})")
    miss = sorted((r for r in rows if r[3] < _HIT), key=lambda r: -r[2])[:6]
    if miss:
        print("pisimmat puuttuvat:", ", ".join(f"{i}({e:.0f}mm)" for i, _, e, _ in miss))


if __name__ == "__main__":
    main(*sys.argv[1:5])

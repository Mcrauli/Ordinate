"""Rohbau3D-GT-vertailu: mallin seinapinnat vs per-piste GT-labelit.

Rohbau3D (open-data.unibw.de, doi:10.60776/ZWJFI4, MIT) antaa per-piste luokat
(Wall / Drywall / Floor / Ceiling / Beam / Column / Window / Door Rough Opening
/ TGA ...). Nain saa mitattua kaksi asiaa joita pelkka pistepilvi ei kerro:

  TARKKUUS  : mallin seinapinnan alla olevien pisteiden GT-luokka. Jos seina on
              oikeassa paikassa, sen kaistassa on Wall/Drywall-pisteita; jos se
              on kalusteen tai palkin paalla, kaistassa on TGA/Beam.
  KATTAVUUS : kuinka suuri osa GT:n Wall-pisteista on jonkin mallin seinan
              kaistassa = paljonko aitoa seinaa jai mallintamatta.

Kaytto: _rohbau_qa.py <model.json> <coord.npy> <class.npy>
"""
import json, sys, pathlib
import collections
import numpy as np

_BAND = 80.0        # mm — kaista mallipinnan ymparilla
_STRUCT = {"Wall", "Drywall", "Parapet", "Facade Element"}
_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}


def main(mj: str, coord_npy: str, class_npy: str) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:          # metrit → mm (sama sääntö kuin loaderissa)
        P *= 1000.0
    assert len(P) == len(C), f"coord {len(P)} != class {len(C)}"

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, cls = P[band][:, :2], C[band]
    print(f"pisteita kaistassa {len(xy):,} / {len(P):,}")

    struct_ids = {k for k, v in _REG.items() if v in _STRUCT}
    is_struct = np.isin(cls, list(struct_ids))
    print(f"GT-rakenteellisia (Wall/Drywall/Parapet/Facade) {int(is_struct.sum()):,}")

    claimed = np.zeros(len(xy), dtype=bool)
    print(f"\n{'wall':13s} {'menet':9s} {'L':>5s} {'t':>4s} | {'n':>8s}  GT-jakauma kaistassa")
    bad = []
    for w in sorted(m["walls"], key=lambda w: -w["thickness"]):
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 800:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a; s = d @ u; t = d @ n
        sel = (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)
        claimed |= sel
        if sel.sum() == 0:
            print(f"{w['id']:13s} {w['source']['method']:9s} {L:5.0f} {w['thickness']:4.0f} | "
                  f"{0:8d}  (tyhja)   <== EI EVIDENSSIA")
            bad.append((w["id"], "tyhja", 0.0))
            continue
        cnt = collections.Counter(cls[sel].tolist())
        tot = int(sel.sum())
        frac_struct = sum(v for k, v in cnt.items() if k in struct_ids) / tot
        top = "  ".join(f"{_REG.get(k, k)}={100 * v / tot:.0f}%" for k, v in cnt.most_common(4))
        flag = ""
        if frac_struct < 0.50:
            flag = "   <== EI SEINAA ALLA"
            bad.append((w["id"], "vaara luokka", frac_struct))
        print(f"{w['id']:13s} {w['source']['method']:9s} {L:5.0f} {w['thickness']:4.0f} | "
              f"{tot:8d}  {top}{flag}")

    recall = float((claimed & is_struct).sum()) / max(int(is_struct.sum()), 1)
    precision = float((claimed & is_struct).sum()) / max(int(claimed.sum()), 1)
    print(f"\nKATTAVUUS  GT-seinapisteista mallin kaistassa: {recall:.3f}")
    print(f"TARKKUUS   mallin kaistan pisteista GT-seinaa : {precision:.3f}")
    print(f"ONGELMASEINIA {len(bad)}"
          + (f": {', '.join(f'{i}({k})' for i, k, _ in bad)}" if bad else ""))
    print(f"aukot: doors={sum(1 for o in m['openings'] if o['opening_type']=='door')} "
          f"windows={sum(1 for o in m['openings'] if o['opening_type']=='window')}")
    gt_win = int((cls == 13).sum() + (cls == 12).sum())
    gt_door = int((cls == 14).sum())
    print(f"GT-aukkopisteita: ikkuna(+cutout)={gt_win:,} ovi-aukko={gt_door:,}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])

"""Ylivenytys per seina: onko seinan PAA katteessa vai ilmassa.

Kattamaton KESKIOSA on laillinen (oviaukko/ikkuna). Kattamaton HANTA tarkoittaa
etta seina on venytetty evidenssin yli (snap/close_open_corners) — ne tuottavat
kaksoisseinia ja valehuoneita.

Kaytto: _extent_qa.py <model.json> <ply|dir> [nimi]
"""
import json, sys, glob, pathlib
import numpy as np

from scan2bim.core.geometry.loader import load_point_cloud

_TOL = 60.0        # mm — pinnan kaista
_BIN = 200.0       # mm
_MIN_PTS = 8       # pisteita binissa jotta se on katettu
_TAIL_FLAG = 700.0 # mm — tata pidempi kattamaton hanta = ylivenytys


def _load_pts(src: str) -> np.ndarray:
    p = pathlib.Path(src)
    if p.is_dir():
        files = sorted(glob.glob(str(p / "scan_*.ply"))) or sorted(glob.glob(str(p / "*.ply")))
        return np.vstack([np.asarray(load_point_cloud(pathlib.Path(f)).points) for f in files])
    return np.asarray(load_point_cloud(p).points)


def run(mj: str, src: str, name: str) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    zf = next(s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor")
    zc = next(s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling")
    P = _load_pts(src)
    xy = P[(P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)][:, :2]

    print(f"\n=== {name}")
    print(f"{'wall':13s} {'menet':9s} {'L':>5s} | {'kate':>5s} {'hanta-A':>8s} {'hanta-B':>8s} "
          f"{'keskirako':>9s}")
    tails = []
    for w in sorted(m["walls"], key=lambda w: -w["thickness"]):
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 800:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a; s = d @ u; t = d @ n
        # kumman tahansa pinnan pisteet kelpaavat katteeksi
        sel = (np.abs(t - w["thickness"] / 2.0) < _TOL) | (np.abs(t + w["thickness"] / 2.0) < _TOL)
        nb = max(int(L / _BIN), 1)
        hist, _ = np.histogram(s[sel], bins=nb, range=(0.0, L))
        cov = hist >= _MIN_PTS
        frac = float(cov.mean())
        if not cov.any():
            print(f"{w['id']:13s} {w['source']['method']:9s} {L:5.0f} | {frac:5.2f} "
                  f"{'KOKO':>8s} {'':>8s} {'':>9s}   <== ei katetta")
            tails.append((L, w["id"], "koko"))
            continue
        first = int(np.argmax(cov)); last = nb - 1 - int(np.argmax(cov[::-1]))
        tail_a = first * _BIN
        tail_b = (nb - 1 - last) * _BIN
        # pisin kattamaton jakso katetun alueen SISALLA
        mid, run_, best = cov[first:last + 1], 0, 0
        for c in mid:
            run_ = 0 if c else run_ + 1
            best = max(best, run_)
        gap = best * _BIN
        flag = ""
        if max(tail_a, tail_b) > _TAIL_FLAG:
            flag = "   <== YLIVENYTYS"
            tails.append((max(tail_a, tail_b), w["id"], "hanta"))
        print(f"{w['id']:13s} {w['source']['method']:9s} {L:5.0f} | {frac:5.2f} "
              f"{tail_a:7.0f}mm {tail_b:7.0f}mm {gap:8.0f}mm{flag}")
    print(f"  YHTEENVETO ylivenytyksia={len(tails)}"
          + (f": {', '.join(f'{i}({v:.0f}mm {k})' for v, i, k in sorted(tails, reverse=True))}"
             if tails else ""))


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[1])

"""Mika kriteeri erottaa HYVAN perimetriseinan HUONOSTA?

Tunnetut tuomiot (GT / _tol_heatmap):
  rohbau ext_007, ext_006 = 100 % Beam      -> HUONO
  rohbau ext_002, ext_003, ext_009 = tyhja  -> HUONO
  rohbau ext_000 (Wall 66 %), ext_001 (87 %) -> HYVA
  asunto ext_000 pinta 1.2 mm                -> HYVA
  asunto ext_002 pinta 58.8 mm, kohina 30.6  -> HUONO

Kaytto: _perim_gate.py <model.json> <pilvi.ply|coord.npy> [nimi]
"""
import json, sys, pathlib
import numpy as np

_BIN = 250.0
_LAT_PAD = 150.0
_MIN_PTS = 5


def _load(src: str) -> np.ndarray:
    p = pathlib.Path(src)
    if p.suffix == ".npy":
        return np.load(p).astype(np.float64) * 1000.0
    from scan2bim.core.geometry.loader import load_point_cloud
    return np.asarray(load_point_cloud(p).points)


def main(mj: str, src: str, name: str) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = _load(src)
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 2700)
    print(f"\n=== {name}   lattia={zf:.0f} katto={zc:.0f}")
    print(f"{'wall':13s} {'L':>5s} | {'pisteita':>8s} {'ankkuri':>8s} {'pysty':>7s}")
    for w in m["walls"]:
        if w["source"]["method"] != "floorplan":
            continue
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 400:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = P[:, :2] - a
        s = d @ u; t = d @ n; z = P[:, 2]
        lat = np.abs(t) < w["thickness"] / 2.0 + _LAT_PAD
        inside = (s > 0) & (s < L) & lat & (z > zf + 100) & (z < zc - 200)
        low = inside & (z < zf + 900)
        nb = max(int(L / _BIN), 1)
        h_any, _ = np.histogram(s[inside], bins=nb, range=(0, L))
        h_low, _ = np.histogram(s[low], bins=nb, range=(0, L))
        # pystyulottuvuus per bini
        vert = np.zeros(nb)
        for k in range(nb):
            mk = inside & (s >= k * L / nb) & (s < (k + 1) * L / nb)
            if int(mk.sum()) >= _MIN_PTS:
                zz = z[mk]
                vert[k] = float(np.percentile(zz, 95) - np.percentile(zz, 5))
        print(f"{w['id']:13s} {L:5.0f} | "
              f"{float((h_any >= _MIN_PTS).mean()):8.2f} "
              f"{float((h_low >= _MIN_PTS).mean()):8.2f} "
              f"{float((vert >= 1000).mean()):7.2f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[1])

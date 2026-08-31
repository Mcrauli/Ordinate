"""Tukeeko pilvi sita suuntaa johon seina on piirretty?

Kellarissa 58 % mallin seinapituudesta kulkee suuntaan jota detektori ei
loytanyt lainkaan, ja kaksi parhaiten tuettua suuntaa on mallinnettu 2.9 m ja
0.0 m. Ne 238 m ovat niita pitkia vinoja linjoja jotka lapaisevat kaikki
portit: ne ovat tasomaisia jossain ja koskettavat pintaa siella taalla.

Mittari: pilven seinamaisten pisteiden NORMAALIEN kulmahistogrammi, ja seinan
oma suunta siita luettuna, suhteessa histogrammin maksimiin. Aito seina on
piirretty suuntaan jossa on pintaa; artefakti ei.

Tama EI ole `drop_skew` uudelleen. Se pudotti seinan joka poikkesi yli 22
astetta PERHESUUNNASTA, eli geometrisesta priorista. Tama lukee saman pilven
mitatun jakauman eika oleta Manhattan-maailmaa: jos rakennuksessa on kuusi
suuntaa, kaikki kuusi nakyvat histogrammissa.

Kaytto: _dir_support_probe.py <model.json> <wallish.npz> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_BIN = 2.0
_TOL = 6.0          # astetta — kuinka lahelta huippua luetaan
_MIN_LEN = 2000.0


def direction_support(model_walls, wallish_xyz):
    """(id -> tuki 0..1) seinan suunnan normaalimassa suhteessa maksimiin."""
    import open3d as o3d

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(wallish_xyz, dtype=np.float64))
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=24))
    n = np.asarray(pc.normals)
    ang = np.degrees(np.arctan2(n[:, 1], n[:, 0])) % 180.0
    nb = int(180.0 / _BIN)
    hist, edges = np.histogram(ang, bins=nb, range=(0.0, 180.0))
    centers = 0.5 * (edges[:-1] + edges[1:])
    peak = float(hist.max())
    if peak <= 0:
        return {}

    out = {}
    for w in model_walls:
        ax = w.get("axis") if isinstance(w, dict) else getattr(w, "axis", None)
        if not ax or len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < _MIN_LEN:
            continue
        d = (np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])) + 90.0) % 180.0
        near = np.abs((centers - d + 90.0) % 180.0 - 90.0) < _TOL
        wid = w["id"] if isinstance(w, dict) else w.id
        out[wid] = (float(hist[near].max()) / peak, L)
    return out


def main(model_json: str, wallish_npz: str, name: str = "") -> None:
    z = np.load(wallish_npz)
    W = z["q"].astype(np.float64)[z["m"]]
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    sup = direction_support(m["walls"], W)
    if not sup:
        print(f"{name}: ei mitattavia")
        return
    v = np.array([s for s, _ in sup.values()])
    L = np.array([l for _, l in sup.values()])
    print(f"{name or model_json:14s} n {len(v):4d}  tuki min {v.min():.2f} "
          f"p10 {np.percentile(v,10):.2f} med {np.median(v):.2f}   "
          f"alle 0.30: {float((v<0.30).mean()):.2f} "
          f"({L[v<0.30].sum()/1000:5.0f} m / {L.sum()/1000:.0f} m)")


if __name__ == "__main__":
    main(*sys.argv[1:])

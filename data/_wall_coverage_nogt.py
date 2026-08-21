"""Seinakattavuus ILMAN ground truthia: malli vs. pilven omat pystypinnat.

`_rohbau_qa.py` mittaa kattavuuden GT-labeleista, joten se toimii vain
Rohbau3D:lla. Asiakaskohteessa labeleita ei ole eika niita tulla saamaan —
silti pitaa tietaa jaiko puolet seinista mallintamatta. Ilman tallaista
mittaria jokainen "6 -> 19 seinaa" -vertailu on arvaus siita kumpi on oikein.

GT:n Wall-pisteiden tilalla on mitattu maski:
  1. normaali on vaakasuora (|nz| < _VERT_NZ)  -> pystypinta
  2. pisteen XY-solussa pystypintaa laajalla z-valilla -> seina, ei kaluste

Kohta 2 on se joka erottaa seinan hyllysta ja tavarasta: hylly on pystypinta
mutta se ei ulotu lattiasta kattoon. Sama sarja mitataan mallin seinakaistasta
tasmalleen kuten `_rohbau_qa.py`, joten luvut ovat vertailukelpoisia.

Validointi: aja Rohbaulla ja vertaa GT-kattavuuteen (`_rohbau_all.py`).

Kaytto: _wall_coverage_nogt.py <model.json> <pilvi.ply|coord.npy>
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

_BAND = 80.0          # mm — kaista mallipinnan ymparilla (sama kuin _rohbau_qa)
_VOXEL = 25.0         # mm — normaalien laskenta harvennetusta pilvesta
_NORMAL_KNN = 30      # naapuria normaalin sovitukseen
_VERT_NZ = 0.35       # |nz| tata pienempi = pystypinta
_CELL = 200.0         # mm — XY-solu pystyjatkuvuuden mittaukseen
_SPAN_FRAC = 0.50     # solun pystypintojen z-valin oltava tama osuus kaistasta
_MIN_CELL_PTS = 8     # solussa oltava nain monta pystypintapistetta
_MIN_WALL_LEN = 800.0 # mm — lyhyempi seina ohitetaan (sama kuin _rohbau_qa)


def _load(path: str) -> np.ndarray:
    p = pathlib.Path(path)
    if p.suffix == ".npy":
        pts = np.load(p).astype(np.float64)
    else:
        import open3d as o3d
        pts = np.asarray(o3d.io.read_point_cloud(str(p)).points)
    if np.ptp(pts[:, 0]) < 500.0:        # metrit -> mm, sama saanto kuin loaderissa
        pts = pts * 1000.0
    return pts


def wallish_mask(pts: np.ndarray, z_lo: float, z_hi: float) -> np.ndarray:
    """Pisteet jotka ovat seinamaisella pystypinnalla kaistassa [z_lo, z_hi]."""
    import open3d as o3d

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    pc = pc.voxel_down_sample(_VOXEL)
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=_NORMAL_KNN))
    q = np.asarray(pc.points)
    nz = np.abs(np.asarray(pc.normals)[:, 2])

    band = (q[:, 2] > z_lo) & (q[:, 2] < z_hi)
    vert = band & (nz < _VERT_NZ)
    if not vert.any():
        return np.zeros(len(q), dtype=bool), q

    ij = np.floor(q[:, :2] / _CELL).astype(np.int64)
    key = ij[:, 0].astype(np.int64) * 10_000_000 + ij[:, 1]
    kv, zv = key[vert], q[vert, 2]
    order = np.argsort(kv, kind="stable")
    kv, zv = kv[order], zv[order]
    edges = np.flatnonzero(np.diff(kv)) + 1
    need = _SPAN_FRAC * (z_hi - z_lo)
    good: list[int] = []
    for k, g in zip(kv[np.concatenate([[0], edges])], np.split(zv, edges)):
        if len(g) >= _MIN_CELL_PTS and (g.max() - g.min()) >= need:
            good.append(int(k))
    return vert & np.isin(key, np.array(good, dtype=np.int64)), q


def main(model_json: str, cloud: str) -> None:
    m = json.loads(pathlib.Path(model_json).read_text(encoding="utf-8"))
    pts = _load(cloud)

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=zf + 2700.0)
    z_lo, z_hi = zf + 400.0, zc - 300.0

    is_wall, q = wallish_mask(pts, z_lo, z_hi)
    xy = q[:, :2]
    print(f"pilvi {len(pts):,} -> tyopilvi {len(q):,}  kaista {z_lo:.0f}..{z_hi:.0f} mm")
    print(f"seinamaisia pystypintapisteita {int(is_wall.sum()):,}")

    claimed = np.zeros(len(q), dtype=bool)
    empty = []
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b[:2] - a[:2]))
        if L < _MIN_WALL_LEN:
            continue
        u = (b[:2] - a[:2]) / L
        n = np.array([-u[1], u[0]])
        d = xy - a[:2]
        s, t = d @ u, d @ n
        sel = (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)
        claimed |= sel
        if not sel.any():
            empty.append(w["id"])

    hit = int((claimed & is_wall).sum())
    recall = hit / max(int(is_wall.sum()), 1)
    precision = hit / max(int(claimed.sum()), 1)
    print(f"\nKATTAVUUS  pystypinnoista mallin kaistassa : {recall:.3f}")
    print(f"TARKKUUS   mallin kaistasta pystypintaa     : {precision:.3f}")
    print(f"seinia mallissa {len(m['walls'])}, evidenssitta {len(empty)}"
          + (f": {', '.join(empty)}" if empty else ""))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

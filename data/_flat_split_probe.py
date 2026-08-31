"""Mita tapahtuu jos seina PILKOTAAN kohdista joissa kaista ei ole taso?

Portit poistavat vain kokonaisia seinia, ja kellarin pitka vino valeseina
lapaisee ne koska se on tasomainen JOSSAIN: 28 m linja joka lavistaa kolmekymmenta
pienta rakennetta saa tasomaisia sarakkeita sielta missa se raapaisee aitoa
pintaa. Oikea operaatio on pilkkominen.

`split_walls_at_gaps` pilkkoo jo, mutta sen todiste ("onko sarakkeessa
pisteita") on kellarissa aina tosi. Tasomaisuus erottelee mitatusti kaikilla
yhdeksalla aineistolla, ja aidot seinat ovat 88-94 % tasomaisia, joten
pilkkominen ei kosketa niita.

Oviaukko ei saa pilkkoa: katkaisu vaatii `_GAP_COLS` perakkaista ei-tasoista
saraketta (500 mm sarake, 3 kpl = 1500 mm > levein oviaukko).

Kaytto: _flat_split_probe.py <model.json> <pilvi.ply> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scan2bim.core.geometry.xy_index import XYIndex, subset  # noqa: E402

_COL = 500.0
_BAND = 120.0
_MIN_PTS = 30
_FLAT_MM = 20.0
_GAP_COLS = 3
_MIN_PIECE = 900.0
_MIN_LEN = 2000.0


def flat_columns(wall_axis, thickness, pts, index):
    """Per-sarake: True = kaista on taso, False = ei, None = ei nayttoa."""
    p0 = np.asarray(wall_axis[0], float)[:2]
    p1 = np.asarray(wall_axis[-1], float)[:2]
    L = float(np.linalg.norm(p1 - p0))
    if L < _MIN_LEN:
        return None, L
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    half = thickness / 2.0
    near, _ = subset(pts, index, p0, u, n, half + _BAND, 0.0, L)
    if len(near) < _MIN_PTS:
        return None, L
    d = near[:, :2] - p0
    s, t = d @ u, d @ n
    n_col = max(int(L / _COL), 1)
    col = np.clip((s / _COL).astype(int), 0, n_col - 1)
    b = min(_BAND, max(half, 20.0))
    out = np.zeros(n_col, dtype=bool)
    for c in range(n_col):
        sel = col == c
        if int(sel.sum()) < _MIN_PTS:
            continue
        tc = t[sel]
        for side in (-half, half):
            band = tc[np.abs(tc - side) < b]
            if len(band) < _MIN_PTS:
                continue
            out[c] = float(np.median(np.abs(band - np.median(band)))) < _FLAT_MM
            break
    return out, L


def split_runs(flat: np.ndarray) -> list[tuple[int, int]]:
    """Palat: yhtenaiset jaksot jotka eivat sisalla _GAP_COLS ei-tasoa perakkain."""
    pieces, start, gap = [], None, 0
    for k in range(len(flat) + 1):
        f = bool(flat[k]) if k < len(flat) else False
        if f:
            if start is None:
                start = k
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= _GAP_COLS or k == len(flat):
                pieces.append((start, k - gap + 1))
                start, gap = None, 0
    return [(a, b) for a, b in pieces if (b - a) * _COL >= _MIN_PIECE]


def main(model_json: str, cloud_path: str, name: str = "") -> None:
    import open3d as o3d

    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    del pc
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"),
             default=float(np.percentile(pts[:, 2], 1)))
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=float(np.percentile(pts[:, 2], 99)))
    lo, hi = zf + 0.25 * (zc - zf), zf + 0.75 * (zc - zf)
    band = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]
    p2 = o3d.geometry.PointCloud()
    p2.points = o3d.utility.Vector3dVector(band)
    band = np.asarray(p2.voxel_down_sample(10.0).points)
    del p2
    index = XYIndex(band)

    tot = kept = 0.0
    n_split = n_gone = 0
    for w in m["walls"]:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        flat, L = flat_columns(ax, float(w["thickness"]), band, index)
        tot += L
        if flat is None:
            kept += L
            continue
        pieces = split_runs(flat)
        klen = sum((b - a) * _COL for a, b in pieces)
        kept += min(klen, L)
        if not pieces:
            n_gone += 1
        elif len(pieces) > 1 or klen < L - _COL:
            n_split += 1
    print(f"{name or model_json:14s} pituus {tot/1000:6.0f} m -> {kept/1000:6.0f} m "
          f"({kept/max(tot,1):.0%})  pilkottu {n_split}  kokonaan pois {n_gone}")


if __name__ == "__main__":
    main(*sys.argv[1:])

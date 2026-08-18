"""Missa palkit katoavat: raakapilvi vs suodatettu pilvi, portti kerrallaan.

`detect_beams` saa putkessa SEMANTTISESTI SUODATETUN pilven. Jos suodatin
pudottaa palkit, mikaan detektorin kynnys ei niita palauta. Tama ajaa saman
kaistanrajauksen ja klusteroinnin molemmille pilville ja tulostaa mihin
porttiin kukin klusteri kaatuu.

Ajo: _beam_probe.py <cloud.ply> <model.json> [--filtered]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scan2bim.core.segmentation import beam_detector as bd  # noqa: E402
from scan2bim.core.segmentation.column_detector import _dist_to_walls  # noqa: E402


def _walls(m):
    from scan2bim.schemas.model import StructuralModel
    return StructuralModel.model_validate(m).walls


def probe(pts: np.ndarray, walls, floor_z: float, ceiling_z: float, has_ceiling: bool, tag: str):
    band_lo = floor_z + 0.5 * (ceiling_z - floor_z)
    if has_ceiling:
        band_lo = max(band_lo, ceiling_z - bd._SOFFIT_BAND)
    zmask = (pts[:, 2] > band_lo) & (pts[:, 2] < ceiling_z - 30.0)
    band = pts[zmask]
    print(f"\n[{tag}] pisteita {len(pts):,}  kaista z>{band_lo:.0f} -> {len(band):,}")
    if not len(band):
        return
    far = _dist_to_walls(band[:, :2], walls) > bd._BEAM_WALL_MARGIN
    free = band[far]
    print(f"[{tag}] seinamarginaalin jalkeen {len(free):,}")
    if len(free) < bd._MIN_INLIERS:
        return
    sub = o3d.geometry.PointCloud()
    sub.points = o3d.utility.Vector3dVector(free)
    det = bd.BeamDetector(sub_ceiling_mm=float(free[:, 2].ptp()) + 100.0,
                          ceiling_z=ceiling_z if has_ceiling else None)
    xy = np.asarray(sub.points).copy()
    xy[:, 2] = 0.0
    flat = o3d.geometry.PointCloud()
    flat.points = o3d.utility.Vector3dVector(xy)
    labels = np.array(flat.cluster_dbscan(eps=det.eps_mm, min_points=det.min_points))
    uniq = [l for l in np.unique(labels) if l >= 0]
    print(f"[{tag}] DBSCAN eps={det.eps_mm} min={det.min_points} -> {len(uniq)} klusteria")
    drop: dict[str, int] = {}
    kept = 0
    rows = []
    for l in sorted(uniq, key=lambda l: -int((labels == l).sum()))[:25]:
        p = free[labels == l]
        why, info = _why(p, det)
        rows.append((l, len(p), why, info))
    for l in uniq:
        p = free[labels == l]
        why, _ = _why(p, det)
        if why == "OK":
            kept += 1
        else:
            drop[why] = drop.get(why, 0) + 1
    print(f"[{tag}] lapi {kept}, hylatty {dict(sorted(drop.items(), key=lambda kv: -kv[1]))}")
    print(f"{'lbl':>5s} {'n':>8s}  {'syy':22s} mitat")
    for l, n, why, info in rows:
        print(f"{l:5d} {n:8d}  {why:22s} {info}")


def _why(p: np.ndarray, det) -> tuple[str, str]:
    if len(p) < bd._MIN_INLIERS:
        return "n < MIN_INLIERS", ""
    xy = p[:, :2]
    c = xy.mean(0)
    _, V = np.linalg.eigh(np.cov((xy - c).T))
    u = V[:, -1]
    proj = (xy - c) @ u
    L = float(proj.ptp())
    w = float(((xy - c) @ V[:, 0]).ptp())
    zd = float(p[:, 2].ptp())
    info = f"L={L:.0f} lev={w:.0f} syv={zd:.0f} zmax={p[:, 2].max():.0f}"
    if L < bd._MIN_LENGTH_MM:
        return "L < MIN_LENGTH", info
    if w > bd._MAX_WIDTH_MM:
        return "leveys > MAX_WIDTH", info
    if w < 10:
        return "leveys < 10", info
    if L / (w + 1e-6) < bd._MIN_ASPECT:
        return "aspekti < MIN_ASPECT", info
    if zd < bd._MIN_HEIGHT_MM:
        return "syvyys < MIN_HEIGHT", info
    if det.ceiling_z is not None:
        if float(p[:, 2].max()) < det.ceiling_z - bd._SOFFIT_ATTACH_MM:
            return "ei soffit-kiinnitysta", info
        if w < bd._FINISHED_MIN_WIDTH_MM:
            return "leveys < FINISHED_MIN", info
    return "OK", info


def main(cloud_path: str, model_json: str) -> None:
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    walls = _walls(m)
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=None)
    has_ceiling = zc is not None
    if zc is None:
        zc = zf + 3000.0
    pcd = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pcd.points, dtype=np.float64)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    print(f"lattia {zf:.0f} katto {zc:.0f} has_ceiling={has_ceiling} seinia {len(walls)}")
    probe(pts, walls, zf, zc, has_ceiling, "raaka")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

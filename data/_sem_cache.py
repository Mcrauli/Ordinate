"""Aja semanttinen suodatin kerran ja tallenna luokat levylle.

PointNet vie kellarilla ~8 min. Jokainen semanttinen koe (kynnykset,
karsintasaannot) tarvitsee samat luokat, joten ne lasketaan kerran ja
luetaan sen jalkeen sekunneissa. Tallennettu muoto on `SemanticLabels`:n
ruudukko, joten `lookup` toimii mille tahansa pistejoukolle.

Kaytto: _sem_cache.py <pilvi.ply> <ulos.npz> [max_pts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.segmentation.pointnet_filter import (  # noqa: E402
    PointNetFilter, SemanticLabels,
)


def load(path) -> SemanticLabels:
    z = np.load(path)
    return SemanticLabels(z["origin"], float(z["voxel"]), z["keys"], z["labels"])


def main(cloud_path: str, out: str, max_pts: str = "14000000") -> None:
    import open3d as o3d
    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points)
    del pc
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    lim = int(max_pts)
    if len(pts) > lim:
        pts = np.ascontiguousarray(pts[:: -(-len(pts) // lim)])
    print(f"pisteita {len(pts):,}", flush=True)

    filt = PointNetFilter()
    if not filt.is_available():
        raise SystemExit("PointNet-mallia ei loydy")
    pred = filt.predict_classes(pts)
    if pred is None:
        raise SystemExit("luokitus epaonnistui")
    lab = SemanticLabels.build(pts, pred)
    np.savez_compressed(out, origin=lab._origin, voxel=lab._voxel,
                        keys=lab._keys, labels=lab._labels)
    names = ["ceiling", "floor", "wall", "beam", "column", "window", "door",
             "table", "chair", "sofa", "bookcase", "board", "clutter"]
    cnt = np.bincount(pred[pred >= 0], minlength=13)
    for i, c in enumerate(cnt):
        if c:
            print(f"  {i:2d} {names[i]:9s} {c:10,d}  {c/cnt.sum():6.1%}")
    print(f"tallennettu {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

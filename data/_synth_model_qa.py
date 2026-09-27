"""Validoi semanttinen suodatinmalli rohbau3d per-piste-GT:tä vasten.

Mittaa: säilyttääkö malli RAKENTEEN (seinä/lattia/katto/palkki/pilari) ja
poistaako se TGA:n (talotekniikka/MEP, luokka 17) ja luokittelemattoman (0).
Vertaa monta mallia (esim. vanha 3DSES vs uusi synteettinen+MEP).

Aja:  .venv\\Scripts\\python.exe data\\_synth_model_qa.py \\
          --scenes 02004 02010 02007 \\
          --models models/_backup_3dses/s3dis_pointnet.onnx models/_new/s3dis_pointnet.onnx
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d

from ordinate.core.segmentation.pointnet_filter import PointNetFilter

from _paths import DOWNLOADS  # portable dev-tool paths

# rohbau3d-luokat → odotettu käytös suodattimessa
_STRUCT = {1: "Ceiling", 2: "SlantCeil", 4: "Floor", 5: "Wall", 6: "Drywall",
           8: "Parapet", 9: "Beam", 10: "Column", 11: "Staircase",
           13: "Window", 15: "Facade", 16: "Elevator"}
_REMOVE = {0: "None/unlabeled", 17: "TGA/MEP"}
_OPENING = {3, 7, 12, 14}   # aukot — ei pisteitä oikeasti, jätetään mittarin ulkopuolelle

_ROHBAU = DOWNLOADS / "rohbau3d" / "extracted" / "site_02"


def _load_scene(scene: str, max_pts: int) -> tuple[np.ndarray, np.ndarray]:
    d = _ROHBAU / f"scene_{scene}"
    xyz = np.load(d / "coord.npy").astype(np.float64) * 1000.0   # m → mm
    cls = np.load(d / "class.npy").astype(np.int64)
    if len(xyz) > max_pts:
        sel = np.random.default_rng(0).choice(len(xyz), max_pts, replace=False)
        xyz, cls = xyz[sel], cls[sel]
    return xyz, cls


def _keep_mask(model_path: Path, pts: np.ndarray) -> np.ndarray:
    filt = PointNetFilter(model_path=model_path)
    if not filt.is_available():
        raise SystemExit(f"Mallia ei voitu ladata: {model_path}")
    return filt._classify(pts)   # True = malli pitää rakenteena


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", nargs="+", default=["02004", "02010", "02007"])
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--max-pts", type=int, default=1_500_000)
    args = ap.parse_args()

    models = [Path(m) for m in args.models]
    for scene in args.scenes:
        pts, cls = _load_scene(scene, args.max_pts)
        struct_gt = np.isin(cls, list(_STRUCT))
        tga_gt = cls == 17
        print(f"\n=== scene {scene}  (n={len(pts)}, rakenne={struct_gt.sum()}, "
              f"TGA={tga_gt.sum()}) ===")
        print(f"{'malli':<40} {'rakenne-säilyy':>14} {'TGA-poisto':>11} {'None-poisto':>11}")
        for mp in models:
            keep = _keep_mask(mp, pts)
            struct_keep = keep[struct_gt].mean() if struct_gt.any() else float("nan")
            tga_rm = (~keep[tga_gt]).mean() if tga_gt.any() else float("nan")
            none_rm = (~keep[cls == 0]).mean() if (cls == 0).any() else float("nan")
            print(f"{mp.parent.name + '/' + mp.name:<40} {struct_keep:>13.1%} "
                  f"{tga_rm:>10.1%} {none_rm:>10.1%}")


if __name__ == "__main__":
    main()

"""Tuotantototeutus vs. validoitu koetin — tuottaako se samat luvut?

Ajo: .venv/Scripts/python.exe data/_support_verify.py <model.json> <cloud>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan2bim.core.qa.deviation import flag_low_confidence, measure_wall_support  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402
from _evidence_probe import metrics  # noqa: E402


def main() -> None:
    mj, cp = sys.argv[1], sys.argv[2]
    model = StructuralModel.load(mj)
    if cp.endswith(".npy"):
        P = np.load(cp).astype(np.float64)
        if np.ptp(P[:, 0]) < 500.0:
            P *= 1000.0
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(P)
    else:
        pcd = o3d.io.read_point_cloud(cp)
        P = np.asarray(pcd.points)
        if np.ptp(P[:, 0]) < 500.0:
            P = P * 1000.0
            pcd.points = o3d.utility.Vector3dVector(P)

    measure_wall_support(model, pcd)
    print(f"{Path(mj).parent.name}: {len(model.walls)} seinää, {len(P):,} pistettä")
    print(f"{'id':14s} {'tuotanto':>9s} {'koetin':>8s} {'ero':>7s}")
    worst = 0.0
    for w in model.walls:
        raw = metrics(w.model_dump(), P)
        ref = raw.get("coverage", float("nan")) if raw else float("nan")
        prod = w.support if w.support is not None else float("nan")
        d = abs(prod - ref) if not (np.isnan(prod) or np.isnan(ref)) else float("nan")
        if not np.isnan(d):
            worst = max(worst, d)
        print(f"{w.id:14s} {prod:9.3f} {ref:8.3f} {d:7.3f}")
    print(f"suurin ero: {worst:.4f}")
    for f in flag_low_confidence(model):
        print(f"  LIPPU {f['id']}: {f.get('reason')}")


if __name__ == "__main__":
    main()

"""Pintapeitto kaikille malleille joille pilvi löytyy — etsi VÄÄRÄT hälytykset.

Ajo: .venv/Scripts/python.exe data/_cov_check.py <model.json> <cloud> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _evidence_probe import metrics  # noqa: E402

THR = 0.15


def load(p: str) -> np.ndarray:
    if p.endswith(".npy"):
        P = np.load(p).astype(np.float64)
    else:
        P = np.asarray(o3d.io.read_point_cloud(p).points)
    if np.ptp(P[:, 0]) < 500.0:
        P = P * 1000.0
    return P


def main() -> None:
    mj, cloud = sys.argv[1], sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else Path(mj).parent.name
    m = json.loads(Path(mj).read_text(encoding="utf-8"))
    P = load(cloud)
    print(f"== {name}: {len(m['walls'])} seinää, {len(P):,} pistettä")
    flagged = []
    for w in m["walls"]:
        mm = metrics(w, P)
        cov = mm.get("coverage", float("nan")) if mm else float("nan")
        bad = (not mm) or np.isnan(cov) or cov < THR
        tag = "LIPPU" if bad else "     "
        print(f"  {tag} {w['id']:14s} L={mm.get('len_m', 0.0):5.1f}m "
              f"conf={w['confidence']:4.2f} peitto={cov:6.3f}")
        if bad:
            flagged.append(w["id"])
    print(f"  -> liputettu {len(flagged)}/{len(m['walls'])}: {flagged}")


if __name__ == "__main__":
    main()

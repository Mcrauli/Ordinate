"""Lisattyjen normals-seinien hyllytasot: Rohbau (aidot) vs retail_s (valeet)."""
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.semantics.wall_semantics import _shelf_levels  # noqa: E402
from ordinate.schemas.model import Wall  # noqa: E402

SETS = {
    "rohbau_07000": "data/_rohbau/site_07/scene_07000/cloud.ply",
    "rohbau_07001": "data/_rohbau/site_07/scene_07001/cloud.ply",
    "rohbau_07002": "data/_rohbau/site_07/scene_07002/cloud.ply",
    "retail_s": "data/_retail_s.ply",
}
for name, ply in SETS.items():
    c = o3d.io.read_point_cloud(ply).voxel_down_sample(0.02 if "rohbau" in name else 20.0)
    P = np.asarray(c.points)
    if np.ptp(P[:, 0]) < 500:
        P = P * 1000.0
    m = json.load(open(f"data/output/_union/{name}/floor_00/model.json", encoding="utf-8"))
    out = []
    for w in m["walls"]:
        if not w["id"].startswith("wall_n_"):
            continue
        W = Wall(**{k: v for k, v in w.items() if k in Wall.model_fields})
        out.append((w["id"], _shelf_levels(W, P)))
    print(name, " ".join(f"{i}:{n}" for i, n in out))

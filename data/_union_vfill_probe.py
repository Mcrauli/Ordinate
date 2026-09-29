"""Lisattyjen normals-seinien pystytaytto lattiasta kattoon: Rohbau vs retail_s."""
import json
import sys

import numpy as np
import open3d as o3d

SETS = {
    "rohbau_07000": "data/_rohbau/site_07/scene_07000/cloud.ply",
    "rohbau_07001": "data/_rohbau/site_07/scene_07001/cloud.ply",
    "rohbau_07002": "data/_rohbau/site_07/scene_07002/cloud.ply",
    "rohbau_07003": "data/_rohbau/site_07/scene_07003/cloud.ply",
    "retail_s": "data/_retail_s.ply",
}
for name, ply in SETS.items():
    c = o3d.io.read_point_cloud(ply)
    P = np.asarray(c.points)
    if np.ptp(P[:, 0]) < 500:
        P = P * 1000.0
    c = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P)).voxel_down_sample(20.0)
    P = np.asarray(c.points)
    m = json.load(open(f"data/output/_union/{name}/floor_00/model.json", encoding="utf-8"))
    fz = min(s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor")
    cz = max(s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling")
    rows = []
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)[:2]; b = np.array(w["axis"][-1], float)[:2]
        L = np.linalg.norm(b - a)
        if L < 500:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = P[:, :2] - a
        t, p = d @ u, np.abs(d @ n)
        sel = (t > 0) & (t < L) & (p < w["thickness"] / 2 + 60)
        z = P[sel, 2]
        bins = np.linspace(fz, cz, 21)
        h, _ = np.histogram(z, bins)
        fill = float((h > 0).mean())
        top = float((np.percentile(z, 98) - fz) / (cz - fz)) if len(z) > 20 else 0.0
        rows.append((w["id"].startswith("wall_n_"), w["id"], round(L), fill, top))
    for new, i, L, f, tp in sorted(rows):
        print(f"{name:13s} {'LISATTY' if new else '       '} {i:16s} L={L:5d} tayte={f:.2f} yla={tp:.2f}")
    print(f"  kerroskorkeus {cz - fz:.0f}")

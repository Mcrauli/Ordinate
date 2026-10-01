"""Ehdokasseinien piirteet pilvesta + GT-tuomio koulutusta varten.

Ehdokkaat = usean ajon valmiiden mallien seinat, duplikaatit pois.
Piirteet lasketaan VAIN pilvesta (ei GT:sta); GT antaa vain tuomion.

Kaytto: _cand_features.py <out.csv> <tag> [<tag> ...]
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _union_probe import covered  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.semantics import wall_verifier as V  # noqa: E402

HERE = Path(__file__).resolve().parent
STRUCT = (5, 6, 8, 15)
FEATS = V.FEATURES


def features(w, q, nz, fz, cz):
    return V._one(w, q, nz, fz, cz)


topo = V._topo


out_csv, tags = sys.argv[1], sys.argv[2:]
rows = []
scenes = sorted({p.parent.parent.name for t in tags for p in (HERE / "output/_wide" / t).glob("scene_*/floor_00/model.json")})
for s in scenes:
    sc = next((HERE / "_rohbau").glob(f"site_*/{s}"))
    cands, ref = [], None
    for t in tags:
        mj = HERE / "output/_wide" / t / s / "floor_00/model.json"
        if not mj.exists():
            continue
        m = json.load(open(mj, encoding="utf-8"))
        ref = ref or m
        for w in m["walls"]:
            a = np.array(w["axis"][0], float); b = np.array(w["axis"][-1], float)
            if np.linalg.norm(b - a) < 800 or covered(w, cands, 150.0):
                continue
            w = dict(w); w["src"] = t
            cands.append(w)
    if ref is None or not cands:
        continue
    fz = min((x["elevation"] for x in ref["slabs"] if x["slab_type"] == "floor"), default=None)
    cz = max((x["elevation"] for x in ref["slabs"] if x["slab_type"] == "ceiling"), default=None)
    if fz is None or cz is None:
        continue
    P = np.load(sc / "coord.npy").astype(float)
    if np.ptp(P[:, 0]) < 500:
        P *= 1000
    C = np.load(sc / "class.npy").ravel()
    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P))
    pc, _, idx = pc.voxel_down_sample_and_trace(25.0, pc.get_min_bound(), pc.get_max_bound())
    rep = np.array([i[0] for i in idx])
    pc.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=24))
    q = np.asarray(pc.points); nz = np.abs(np.asarray(pc.normals)[:, 2]); cq = C[rep]
    band = (q[:, 2] > fz - 200) & (q[:, 2] < cz + 200)
    q, nz, cq = q[band], nz[band], cq[band]
    refw = ref["walls"]
    ref_ids = {x["id"] for x in refw}
    feats = []
    for w in cands:
        f, face = features(w, q, nz, fz, cz)
        f["cross"], f["par_near"] = topo(w, [x for x in refw if x["id"] != w["id"]])
        f["in_ref"] = float(w["src"] == tags[0] and w["id"] in ref_ids)
        gt = float(np.isin(cq[face & (((q[:, 2] - fz) / (cz - fz) > 0.1) & ((q[:, 2] - fz) / (cz - fz) < 0.9))], STRUCT).mean()) if face.any() else 0.0
        feats.append((w, f, gt))
    med_n = np.median([f["npts"] for _, f, _ in feats]) or 1.0
    med_d = np.median([f["dens"] for _, f, _ in feats]) or 1.0
    for w, f, gt in feats:
        f["npts_rel"] = f["npts"] / med_n; f["dens_rel"] = f["dens"] / med_d
        rows.append([s, s.split("_")[1][:2], w["id"], w["src"], round(gt, 3)] + [round(float(f[k]), 4) for k in FEATS])
    print(s, len(cands), "ehdokasta", flush=True)
with open(out_csv, "w", newline="", encoding="utf-8") as fh:
    wr = csv.writer(fh); wr.writerow(["scene", "site", "id", "src", "gtfrac"] + FEATS); wr.writerows(rows)
print("rivit", len(rows))

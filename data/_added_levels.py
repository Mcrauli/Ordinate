"""Lisattyjen normals-seinien hyllytasot vs GT-seinaosuus (portaat/palkit vs aidot)."""
import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.semantics.wall_semantics import _shelf_levels  # noqa: E402
from ordinate.schemas.model import Wall  # noqa: E402

tag = sys.argv[1]
for mj in sorted(Path(f"data/output/_wide/{tag}").glob("scene_*/floor_00/model.json")):
    s = mj.parent.parent.name
    sc = next(Path("data/_rohbau").glob(f"site_*/{s}"))
    m = json.load(open(mj, encoding="utf-8"))
    adds = [w for w in m["walls"] if w["id"].startswith("wall_n_")]
    if not adds:
        continue
    P = np.load(sc / "coord.npy").astype(float)
    if np.ptp(P[:, 0]) < 500:
        P *= 1000
    C = np.load(sc / "class.npy").ravel()
    sub = np.random.default_rng(0).choice(len(P), min(len(P), 3_000_000), replace=False)
    P, C = P[sub], C[sub]
    zf = min(x["elevation"] for x in m["slabs"] if x["slab_type"] == "floor")
    zc = max(x["elevation"] for x in m["slabs"] if x["slab_type"] == "ceiling")
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    for w in adds:
        W = Wall(**{k: v for k, v in w.items() if k in Wall.model_fields})
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][-1], float)
        L = np.linalg.norm(b - a); u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = P[band, :2] - a; t, p = d @ u, np.abs(d @ n)
        k = (t > 0) & (t < L) & (np.abs(p - w["thickness"] / 2) < 80)
        c = C[band][k]
        wf = float(np.isin(c, (5, 6, 8, 15)).mean()) if len(c) else 0.0
        print(f"{s} {w['id']:12s} L={L/1000:4.1f} tasot={_shelf_levels(W, P):2d} GTseina={wf:.2f} {'VAARA' if wf < 0.5 else ''}")

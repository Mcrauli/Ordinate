"""Suuntahistogrammi scenessa + GT-seinien suunnan tuki (direction_prune)."""
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.semantics.contrast_prune import wallish_of  # noqa: E402
from ordinate.core.semantics.direction_prune import _histogram  # noqa: E402

sc = Path(sys.argv[1]); mj = sys.argv[2]
m = json.load(open(mj, encoding="utf-8"))
fz = min(x["elevation"] for x in m["slabs"] if x["slab_type"] == "floor")
cz = max(x["elevation"] for x in m["slabs"] if x["slab_type"] == "ceiling")
P = np.load(sc / "coord.npy").astype(float) * 1000.0
pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P)).voxel_down_sample(20.0)
mask, q = wallish_of(pc, fz, cz)
W = q[mask]
hist, cen = _histogram(W)
top = np.argsort(hist)[::-1][:8]
print("wallish", len(W), "huiput:", [(round(float(cen[i])), round(float(hist[i] / hist.max()), 2)) for i in top])
C = np.load(sc / "class.npy").ravel(); I = np.load(sc / "instance.npy").ravel()
Pw = P[np.isin(C, (5, 6))]; Iw = I[np.isin(C, (5, 6))]
for i in np.unique(Iw):
    X = Pw[Iw == i][:, :2]
    if len(X) < 2000: continue
    c = X.mean(0); ev, V = np.linalg.eigh(np.cov((X - c).T))
    L = np.ptp((X - c) @ V[:, 1])
    if L < 2000: continue
    ang = np.degrees(np.arctan2(V[1, 1], V[0, 1]))
    deg = (ang + 90) % 180
    near = np.abs((cen - deg + 90) % 180 - 90) < 6
    print(f"inst {i:3d} L={L/1000:4.1f} normaali {deg:5.1f}  tuki {hist[near].max()/hist.max():.2f}")

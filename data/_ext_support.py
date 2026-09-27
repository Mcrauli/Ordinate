import json
import numpy as np

P = np.load(r"C:\Users\lauri\scan2bim\data\_work_cloud.npy")
m = json.load(open(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json", encoding="utf-8"))
zf, zc = -25902.0, -23216.0
xy, z = P[:, :2], P[:, 2]

print(f"{'wall':13s} {'method':10s} {'t':>5s} {'L':>6s}  faces/axis point support (raakapisteet, z=lattia+400..katto-300)")
for w in m["walls"]:
    a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L; n = np.array([-u[1], u[0]])
    d = xy - a; s = d @ u; t = d @ n
    band = (z > zf + 400) & (z < zc - 300) & (s > 100) & (s < L - 100)
    th = w["thickness"]
    def cnt(c, tol=80.0):
        return int((band & (np.abs(t - c) < tol)).sum())
    n_ax = cnt(0.0, th / 2 + 50)
    n_f1 = cnt(+th / 2); n_f2 = cnt(-th / 2)
    # kate: kuinka suuri osa seinan pituudesta on pisteiden peitossa
    seg = band & (np.abs(t) < th / 2 + 80)
    nb = max(int(L // 250), 1)
    hh, _ = np.histogram(s[seg], bins=nb, range=(0, L))
    cov = float((hh > 15).mean())
    print(f"{w['id']:13s} {w['source']['method']:10s} {th:5.0f} {L:6.0f}  "
          f"axis={n_ax:8d} f+={n_f1:8d} f-={n_f2:8d} cov={cov:.2f}")

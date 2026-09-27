import json
import numpy as np

P = np.load(r"C:\Users\lauri\scan2bim\data\_work_cloud.npy")
m = json.load(open(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json", encoding="utf-8"))
zf, zc = -25902.0, -23216.0

w10 = next(w for w in m["walls"] if w["id"] == "wall_010")
a = np.array(w10["axis"][0], float); b = np.array(w10["axis"][1], float)
u = (b - a) / np.linalg.norm(b - a); n = np.array([-u[1], u[0]])
d = P[:, :2] - a
s = d @ u; t = d @ n; z = P[:, 2]

print("=== hieno lateraaliprofiili wall_010 (25mm), z-kaistoittain, s=2000..8000 ===")
sel0 = (s > 2000) & (s < 8000)
edges = np.arange(-600, 1025, 25)
for zlo, zhi, lab in [(zf - 500, zf + 100, "lattia"), (zf + 100, zf + 800, "alaosa"),
                      (zf + 800, zf + 1800, "vyotaro"), (zf + 1800, zc - 200, "ylaosa"),
                      (zc - 200, zc + 500, "katto")]:
    sel = sel0 & (z >= zlo) & (z < zhi)
    h, _ = np.histogram(t[sel], bins=edges)
    mx = max(h.max(), 1)
    row = "".join("#" if c > mx*0.5 else "+" if c > mx*0.15 else "." if c > mx*0.03 else " " for c in h)
    print(f"{lab:8s} n={sel.sum():7d} |{row}| max={mx}")
print(" " * 20 + "".join("^" if e % 200 == 0 else " " for e in edges[:-1]))
print(" " * 20 + "t = -600 .. 1000, ^ joka 200mm; ext_001 @ t=+638")

print("\n=== ext_001 kaista t=500..800: pisteita korkeussuunnassa ===")
sel = sel0 & (t > 500) & (t < 800)
print("n =", sel.sum())

print("\n=== wall_010 pinnat: piikit ===")
sel = sel0 & (z > zf + 400) & (z < zc - 300)
h, e = np.histogram(t[sel], bins=np.arange(-600, 600, 10))
top = np.argsort(h)[::-1][:8]
for i in sorted(top):
    print(f"  t={e[i]:6.0f} n={h[i]}")

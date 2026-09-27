"""Fysikaalinen invariantti: seinan RUNGON sisalla ei voi olla lattia- eika
kattopisteita (laatta loppuu seinan pintaan). Jos on, paksuus/akseli on vaarin."""
import json
import numpy as np

P = np.load(r"C:\Users\lauri\scan2bim\data\_work_cloud.npy")
m = json.load(open(r"C:\Users\lauri\scan2bim\data\output\_v088_ifc\floor_00\model.json", encoding="utf-8"))
zf, zc = -25902.0, -23216.0
xy, z = P[:, :2], P[:, 2]
mflo = (z > zf - 150) & (z < zf + 250)
mcei = (z > zc - 250) & (z < zc + 150)

print(f"{'wall':13s} {'t':>5s} {'L':>6s} | lattia/katto RUNGON sisalla (osuus pituudesta)")
for w in m["walls"]:
    a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(b - a)); u = (b - a) / L; n = np.array([-u[1], u[0]])
    th = w["thickness"]
    inner = th / 2 - 60.0          # marginaali pinnan kohinalle
    if inner <= 20:
        inner = th / 2 * 0.5
    nb = max(int(L // 250), 1)
    res = []
    for msk, lab in ((mflo, "lattia"), (mcei, "katto")):
        d = xy[msk] - a
        s = d @ u; t = d @ n
        sel = (s > 150) & (s < L - 150) & (np.abs(t) < inner)
        hh, _ = np.histogram(s[sel], bins=nb, range=(0, L))
        res.append(float((hh > 8).mean()))
    print(f"{w['id']:13s} {th:5.0f} {L:6.0f} | lattia={res[0]:.2f} katto={res[1]:.2f}"
          + ("   <== RUNKO EI OLE TYHJA" if max(res) > 0.35 else ""))

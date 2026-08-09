"""ROUND-TRIP-VALIDOINTI: tunnettu malli -> puhdas 2-puolinen pilvi -> pipeline ->
vertaa palautus tunnettuun. Erottaa ALGORITMIN tarkkuuden DATAN rajasta (occluusio).

Generoi pilven nykyisen model.json:n seinistä (molemmat pinnat, koko korkeus, ei
kalusteita, ei occluusiota, 2mm kohina) ja ajaa SAMAN contour-pipelinen.

Aja: PYTHONPATH=src .venv/Scripts/python data/_synth_roundtrip.py
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import open3d as o3d
from _paths import REPO  # portable dev-tool paths

ROOT = Path(str(REPO))
MODEL = ROOT / "data" / "output" / "_contour_ifc" / "floor_00" / "model.json"
SYNTH = ROOT / "data" / "_synth.ply"
OUT = ROOT / "data" / "output" / "_synth_ifc"

NOISE_MM = 2.0
STEP_MM = 25.0   # pisteväli pinnoilla


def _plane(p0, p1, z0, z1, offset_n, rng):
    """Sampleaa seinän yhden pinnan (akseli p0-p1 siirretty offset_n normaalin suuntaan)."""
    u = (p1 - p0); L = np.linalg.norm(u)
    if L < 1: return np.empty((0, 3))
    u = u / L; n = np.array([-u[1], u[0]])
    base0 = p0 + offset_n * n
    na = int(L / STEP_MM) + 1; nz = int((z1 - z0) / STEP_MM) + 1
    s = np.linspace(0, L, na); zz = np.linspace(z0, z1, nz)
    S, Z = np.meshgrid(s, zz)
    pts = base0[None, :] + S.ravel()[:, None] * u[None, :]
    out = np.column_stack([pts[:, 0], pts[:, 1], Z.ravel()])
    return out + rng.normal(0, NOISE_MM, out.shape)


def build_cloud(walls, floor_z, ceil_z, rng):
    parts = []
    for w in walls:
        p0 = np.array(w["axis"][0], float); p1 = np.array(w["axis"][1], float)
        t = w["thickness"]
        parts.append(_plane(p0, p1, floor_z + 50, ceil_z - 50, +t / 2, rng))  # pinta A
        parts.append(_plane(p0, p1, floor_z + 50, ceil_z - 50, -t / 2, rng))  # pinta B
    # lattia + katto (suorakaide bounding)
    allp = np.vstack(parts)
    x0, y0 = allp[:, 0].min() - 200, allp[:, 1].min() - 200
    x1, y1 = allp[:, 0].max() + 200, allp[:, 1].max() + 200
    nx = int((x1 - x0) / 40) + 1; ny = int((y1 - y0) / 40) + 1
    X, Y = np.meshgrid(np.linspace(x0, x1, nx), np.linspace(y0, y1, ny))
    for z in (floor_z, ceil_z):
        fl = np.column_stack([X.ravel(), Y.ravel(), np.full(X.size, z)])
        parts.append(fl + rng.normal(0, NOISE_MM, fl.shape))
    return np.vstack(parts)


def _line_int(p1, d1, p2, d2):
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]]); b = np.array([p2[0]-p1[0], p2[1]-p1[1]])
    if abs(np.linalg.det(A)) < 1e-9: return None
    t = np.linalg.solve(A, b); return p1 + t[0]*d1


def corners(walls):
    """Kaikki kohtisuorat seinä-seinä-leikkaukset (akselien)."""
    arr = []
    for w in walls:
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        d = b-a; L = np.linalg.norm(d)
        if L > 1: arr.append((a, d/L, L))
    cs = []
    for i in range(len(arr)):
        for j in range(i+1, len(arr)):
            if abs(np.dot(arr[i][1], arr[j][1])) > 0.3: continue
            pt = _line_int(arr[i][0], arr[i][1], arr[j][0], arr[j][1])
            if pt is None: continue
            ti = np.dot(pt-arr[i][0], arr[i][1]); tj = np.dot(pt-arr[j][0], arr[j][1])
            if -300 < ti < arr[i][2]+300 and -300 < tj < arr[j][2]+300:
                cs.append(pt)
    return cs


def main():
    m = json.loads(MODEL.read_text())
    walls = [w for w in m["walls"] if np.linalg.norm(np.array(w["axis"][1])-np.array(w["axis"][0])) > 1]
    fz = min(w["z_min"] for w in walls)
    cz = fz + max(w["height"] for w in walls)
    rng = np.random.default_rng(0)
    pts_mm = build_cloud(walls, fz, cz, rng)
    print(f"synteettinen pilvi: {len(pts_mm)} pistettä")
    pc = o3d.geometry.PointCloud(); pc.points = o3d.utility.Vector3dVector(pts_mm / 1000.0)  # m
    o3d.io.write_point_cloud(str(SYNTH), pc)

    from scan2bim.core.pipeline import Pipeline, PipelineConfig
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=True, export_dxf=False, export_qa=False)
    models = Pipeline(cfg).run_floors([SYNTH], OUT)
    rec = json.loads((OUT / "floor_00" / "model.json").read_text())
    rwalls = [w for w in rec["walls"] if np.linalg.norm(np.array(w["axis"][1])-np.array(w["axis"][0])) > 1]
    print(f"TUNNETTU walls={len(walls)}  PALAUTETTU walls={len(rwalls)}")

    # paksuus: lähin tunnettu seinä per palautettu (keskipisteen mukaan)
    tmid = [(0.5*(np.array(w['axis'][0])+np.array(w['axis'][1])), w['thickness']) for w in walls]
    terr = []
    for w in rwalls:
        mid = 0.5*(np.array(w['axis'][0])+np.array(w['axis'][1]))
        km, kt = min(tmid, key=lambda x: np.linalg.norm(x[0]-mid))
        if np.linalg.norm(km-mid) < 800: terr.append(abs(w['thickness']-kt))
    # nurkat: lähin tunnettu nurkka per palautettu nurkka
    kc = corners(walls); rc = corners(rwalls)
    cerr = [min(np.linalg.norm(r-k) for k in kc) for r in rc] if kc and rc else []

    def st(name, v, unit="mm"):
        if not v: print(f"  {name}: ei dataa"); return
        a = np.array(v); print(f"  {name}: mediaani={np.median(a):.2f}{unit} keski={a.mean():.2f}{unit} <1.5={100*np.mean(a<1.5):.0f}% <5={100*np.mean(a<5):.0f}% (n={len(a)})")
    print("ROUND-TRIP (puhdas 2-puolinen, EI occluusiota):")
    st("PAKSUUSVIRHE", terr)
    st("NURKKAVIRHE", cerr)

    # per-seinä KULMAVIRHE: matchaa palautettu lähimpään tunnettuun, vertaa suuntaa
    def ang(w):
        d = np.array(w['axis'][1], float) - np.array(w['axis'][0], float)
        return np.degrees(np.arctan2(d[1], d[0])) % 180.0
    kinfo = [(0.5*(np.array(w['axis'][0])+np.array(w['axis'][1])), ang(w), np.linalg.norm(np.array(w['axis'][1])-np.array(w['axis'][0]))) for w in walls]
    aerr_all, aerr_short, aerr_long = [], [], []
    for w in rwalls:
        mid = 0.5*(np.array(w['axis'][0])+np.array(w['axis'][1]))
        km, ka, kl = min(kinfo, key=lambda x: np.linalg.norm(x[0]-mid))
        if np.linalg.norm(km-mid) > 800: continue
        da = abs(ang(w)-ka); da = min(da, 180-da)
        aerr_all.append(da)
        (aerr_short if kl < 1500 else aerr_long).append(da)
    st("KULMAVIRHE kaikki", aerr_all, "°")
    st("KULMAVIRHE lyhyet<1.5m", aerr_short, "°")
    st("KULMAVIRHE pitkat>=1.5m", aerr_long, "°")


if __name__ == "__main__":
    main()

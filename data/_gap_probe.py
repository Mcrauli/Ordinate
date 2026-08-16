"""MIKÄ jää mallintamatta? Kattavuuden 0.792 puuttuva viidennes paloina.

`_rohbau_qa.py` kertoo yhden luvun. Se ei kerro onko vaje (a) kokonaan
puuttuvia pitkiä seiniä, (b) seinien päitä ja aukkojen reunoja vai (c) ohutta
sirontaa kaikkialla — ja korjaus on joka tapauksessa eri. Tämä ryhmittelee
LUNASTAMATTOMAT GT-seinäpisteet ja tulostaa palat kokojärjestyksessä.

Ajo: .venv/Scripts/python.exe data/_gap_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_BAND = 80.0        # mm — sama kaista kuin _rohbau_qa:ssa
_STRUCT = {"Wall", "Drywall", "Parapet", "Facade Element"}
_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}

MODEL = Path("data/output/_rohbau_site_07_scene_07000/floor_00/model.json")
SCENE = Path("data/_rohbau/site_07/scene_07000")


def main() -> None:
    m = json.loads(MODEL.read_text(encoding="utf-8"))
    P = np.load(SCENE / "coord.npy").astype(np.float64)
    C = np.load(SCENE / "class.npy").ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    P, C = P[band], C[band]
    struct_ids = [k for k, v in _REG.items() if v in _STRUCT]
    gt = np.isin(C, struct_ids)
    G = P[gt]
    print(f"GT-seinäpisteitä kaistassa {len(G):,}")

    claimed = np.zeros(len(G), bool)
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = G[:, :2] - a
        s, t = d @ u, d @ n
        claimed |= (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)
    miss = G[~claimed]
    print(f"lunastettu {claimed.mean():.3f} -- puuttuu {len(miss):,} pistettä\n")

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(miss)
    pc = pc.voxel_down_sample(100.0)
    Q = np.asarray(pc.points)
    lab = np.array(pc.cluster_dbscan(eps=400.0, min_points=10, print_progress=False))
    n_cl = lab.max() + 1
    print(f"{len(Q):,} voxelia (100 mm), {n_cl} palaa\n")

    rows = []
    for i in range(n_cl):
        Qi = Q[lab == i]
        if len(Qi) < 20:
            continue
        xy = Qi[:, :2] - Qi[:, :2].mean(0)
        _, _, vt = np.linalg.svd(xy, full_matrices=False)
        proj = xy @ vt[0]
        rows.append((len(Qi), float(np.ptp(proj)), float(np.ptp(xy @ vt[1])),
                     float(np.ptp(Qi[:, 2])), Qi[:, :2].mean(0), Qi[:, 2].min()))
    rows.sort(reverse=True)
    tot = sum(r[0] for r in rows)
    print(f"{'#':>3s} {'voxelia':>8s} {'osuus':>6s} {'pituus':>8s} {'leveys':>7s} "
          f"{'korkeus':>8s} {'keskipiste':>20s}")
    for k, (n, ln, wd, ht, ctr, z0) in enumerate(rows[:15]):
        print(f"{k:3d} {n:8d} {n / max(tot, 1):6.1%} {ln / 1000:7.1f}m {wd / 1000:6.1f}m "
              f"{ht / 1000:7.1f}m   ({ctr[0] / 1000:7.1f},{ctr[1] / 1000:7.1f}) z={z0 / 1000:.1f}")
    print(f"\n15 suurinta = {sum(r[0] for r in rows[:15]) / max(tot, 1):.1%} vajeesta, "
          f"loput {len(rows) - 15 if len(rows) > 15 else 0} palaa hajallaan")


if __name__ == "__main__":
    main()

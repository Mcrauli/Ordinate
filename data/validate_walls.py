"""
Validoi havaittujen seinien geometria pistepilveä vasten.
Käyttö: python data/validate_walls.py data/output/apt_normals2/model.json apt.ply
"""
from __future__ import annotations

import sys
import json
import numpy as np
import open3d as o3d


def validate(json_path: str, ply_path: str) -> None:
    with open(json_path, encoding="utf-8") as f:
        model = json.load(f)
    walls = model["walls"]

    cloud = o3d.io.read_point_cloud(ply_path)
    pts = np.asarray(cloud.points)

    span = pts.max(axis=0) - pts.min(axis=0)
    if span.max() < 200:
        pts = pts * 1000.0
        print("[autoscale] metrit -> mm")

    print(f"Pilvi: {len(pts):,} pist., X=[{pts[:,0].min():.0f},{pts[:,0].max():.0f}] "
          f"Y=[{pts[:,1].min():.0f},{pts[:,1].max():.0f}] Z=[{pts[:,2].min():.0f},{pts[:,2].max():.0f}]")
    print()

    PLANE_TOL = 1.5    # mm — pisteestä lasketaan "seinällä" jos alle tämän etäisyydellä

    print(f"{'ID':<12} {'Pituus':>8} {'Paksuus':>8}  {'Seinäpist':>10}  {'Peitto%':>8}  Arvio")
    print("-" * 65)

    for w in walls:
        ax = w["axis"]
        p0 = np.array([ax[0][0], ax[0][1]])
        p1 = np.array([ax[1][0], ax[1][1]])
        d = p1 - p0
        length = float(np.linalg.norm(d))
        if length < 1:
            continue
        d_n = d / length
        normal = np.array([-d_n[1], d_n[0]])

        # Etäisyys tasosta (2D normaali)
        D = float(np.dot(normal, p0))
        plane_dist = np.abs(pts[:, :2] @ normal - D)

        # Projektioperustaiset suodattimet
        proj_along = (pts[:, :2] - p0) @ d_n
        in_bounds = (proj_along >= -200) & (proj_along <= length + 200)

        z_min = w.get("z_min", 0.0)
        z_max = z_min + w.get("height", 2500.0)
        in_z = (pts[:, 2] >= z_min - 200) & (pts[:, 2] <= z_max + 200)

        # Pisteet seinätasolla
        on_plane = plane_dist < PLANE_TOL
        wall_pts_mask = on_plane & in_bounds & in_z

        n_wall = int(wall_pts_mask.sum())

        # Peittoaste: kuinka suuri osa seinäpituudesta on pisteitä
        if n_wall > 0:
            projs = proj_along[wall_pts_mask]
            # Jaa seinä 10 segmenttiin, tarkista montako on peitetty
            n_seg = 10
            covered = 0
            seg_len = length / n_seg
            for s in range(n_seg):
                lo = s * seg_len - 200
                hi = (s + 1) * seg_len + 200
                if np.any((projs >= lo) & (projs <= hi)):
                    covered += 1
            coverage = covered / n_seg * 100
        else:
            coverage = 0.0

        if coverage >= 80 and n_wall > 500:
            status = "HYVA"
        elif coverage >= 50 and n_wall > 100:
            status = "OK"
        elif coverage >= 30:
            status = "HEIKKO"
        else:
            status = "HUONO"

        print(f"{w['id']:<12} {length:>8.0f} {w.get('thickness',0):>8.0f}  "
              f"{n_wall:>10,}  {coverage:>8.0f}%  {status}")

    # Koordinaattivertailu
    wall_xs = [p for w in walls for p in [w['axis'][0][0], w['axis'][1][0]]]
    wall_ys = [p for w in walls for p in [w['axis'][0][1], w['axis'][1][1]]]
    print()
    if wall_xs:
        wx0, wx1 = min(wall_xs), max(wall_xs)
        wy0, wy1 = min(wall_ys), max(wall_ys)
        px0, px1 = float(pts[:,0].min()), float(pts[:,0].max())
        py0, py1 = float(pts[:,1].min()), float(pts[:,1].max())
        print(f"Seinat: X=[{wx0:.0f},{wx1:.0f}] Y=[{wy0:.0f},{wy1:.0f}]")
        print(f"Pilvi:  X=[{px0:.0f},{px1:.0f}] Y=[{py0:.0f},{py1:.0f}]")
        dx = max(abs(wx0-px0), abs(wx1-px1))
        dy = max(abs(wy0-py0), abs(wy1-py1))
        print(f"Koordinaattipoikkeama: X={dx:.0f}mm  Y={dy:.0f}mm")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Kaytto: python validate_walls.py <model.json> <pilvi.ply>")
        sys.exit(1)
    validate(sys.argv[1], sys.argv[2])

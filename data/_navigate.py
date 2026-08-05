"""Liiku skannimaailmassa: varillinen pistepilvi + detektoitu malli paallekkain
INTERAKTIIVISESSA 3D-ikkunassa (pyorita/zoomaa hiirella). Cintoo-tyylinen
tarkistus jolla nakee OIKEASTI ollaanko lahella totuutta.

Kaytto:
  python data/_navigate.py <e57|ply> <model.json> [max_points]

Hiiri: vasen=pyorita, rulla=zoom, oikea=siirra. Malli: seinat syaani,
aukot punainen, pilarit keltainen, palkit vihrea.
"""
import sys
import json
from pathlib import Path

import numpy as np
import open3d as o3d

from scan2bim.core.geometry.loader import load_point_cloud


def _lineset(points, lines, color):
    ls = o3d.geometry.LineSet()
    ls.points = o3d.utility.Vector3dVector(np.asarray(points, float))
    ls.lines = o3d.utility.Vector2iVector(np.asarray(lines, int))
    ls.colors = o3d.utility.Vector3dVector(np.tile(color, (len(lines), 1)))
    return ls


def _box_edges(pts):
    """pts: 8 kulmaa (alaneljä, ylaneljä) -> 12 reunaa (indeksipareina + pisteet)."""
    lines = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    return pts, lines


def wall_geoms(model):
    P, L = [], []
    for w in model["walls"]:
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        z0 = w.get("z_min", 0.0); z1 = z0 + w["height"]
        base = len(P)
        P += [[x0, y0, z0], [x1, y1, z0], [x1, y1, z1], [x0, y0, z1]]
        L += [(base, base + 1), (base + 1, base + 2), (base + 2, base + 3), (base + 3, base)]
    return _lineset(P, L, [0.0, 0.8, 1.0]) if P else None


def opening_geoms(model, wall_by_id):
    P, L = [], []
    for op in model.get("openings", []):
        w = wall_by_id.get(op["wall_id"])
        if not w:
            continue
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        d = np.array([x1 - x0, y1 - y0]); Ln = np.linalg.norm(d)
        if Ln < 1:
            continue
        u = d / Ln
        a0 = op["position_along"]; a1 = a0 + op["width"]
        zf = w.get("z_min", 0.0); z0 = zf + op["sill_height"]; z1 = z0 + op["opening_height"]
        pa = np.array([x0, y0]) + u * a0; pb = np.array([x0, y0]) + u * a1
        base = len(P)
        P += [[pa[0], pa[1], z0], [pb[0], pb[1], z0], [pb[0], pb[1], z1], [pa[0], pa[1], z1]]
        L += [(base, base + 1), (base + 1, base + 2), (base + 2, base + 3), (base + 3, base)]
    return _lineset(P, L, [1.0, 0.1, 0.1]) if P else None


def column_geoms(model):
    P, L = [], []
    for c in model.get("columns", []):
        x, y = c["location"]; z0 = c["base_z"]; z1 = z0 + c["height"]
        pr = c["profile"]; wx = pr["width"] / 2; wy = pr["depth"] / 2
        base = len(P)
        for zz in (z0, z1):
            P += [[x - wx, y - wy, zz], [x + wx, y - wy, zz],
                  [x + wx, y + wy, zz], [x - wx, y + wy, zz]]
        for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                     (0, 4), (1, 5), (2, 6), (3, 7)]:
            L.append((base + a, base + b))
    return _lineset(P, L, [1.0, 0.85, 0.0]) if P else None


def beam_geoms(model):
    P, L = [], []
    for b in model.get("beams", []):
        a, c = b["axis"][0], b["axis"][1]
        base = len(P)
        P += [list(a), list(c)]
        L.append((base, base + 1))
    return _lineset(P, L, [0.1, 0.9, 0.2]) if P else None


def main():
    src = Path(sys.argv[1]); model_path = Path(sys.argv[2])
    max_pts = int(sys.argv[3]) if len(sys.argv) > 3 else 3_000_000
    cloud = load_point_cloud(src)
    P = np.asarray(cloud.points)
    step = max(1, len(P) // max_pts)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(P[::step])
    if cloud.has_colors():
        C = np.asarray(cloud.colors)[::step]
        pcd.colors = o3d.utility.Vector3dVector(C)
    print(f"pilvi {len(P)} -> naytetaan {len(pcd.points)} pistetta")

    model = json.load(open(model_path))
    wall_by_id = {w["id"]: w for w in model["walls"]}
    geoms = [pcd]
    for g in (wall_geoms(model), opening_geoms(model, wall_by_id),
              column_geoms(model), beam_geoms(model)):
        if g is not None:
            geoms.append(g)
    print(f"malli: {len(model['walls'])} seinaa, {len(model.get('openings', []))} aukkoa, "
          f"{len(model.get('columns', []))} pilaria, {len(model.get('beams', []))} palkkia")
    o3d.visualization.draw_geometries(geoms, window_name="scan2bim navigointi", width=1600, height=1000)


if __name__ == "__main__":
    main()

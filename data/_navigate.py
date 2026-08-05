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


def _box_mesh(center, size, angle, color):
    """Orientoitu laatikkomesh: keskipiste, koko (dx,dy,dz), Z-kierto, vari."""
    sx, sy, sz = (max(float(s), 1.0) for s in size)
    b = o3d.geometry.TriangleMesh.create_box(sx, sy, sz)
    b.translate((-sx / 2, -sy / 2, -sz / 2))
    R = b.get_rotation_matrix_from_xyz((0.0, 0.0, angle))
    b.rotate(R, center=(0, 0, 0))
    b.translate(center)
    b.compute_vertex_normals()
    b.paint_uniform_color(color)
    return b


def wall_geoms(model):
    """Seinat umpinaisina laatikkoina (pituus x paksuus x korkeus)."""
    meshes = []
    for w in model["walls"]:
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        z0 = w.get("z_min", 0.0); h = w["height"]
        dx, dy = x1 - x0, y1 - y0
        length = float(np.hypot(dx, dy))
        if length < 1:
            continue
        angle = float(np.arctan2(dy, dx))
        center = ((x0 + x1) / 2, (y0 + y1) / 2, z0 + h / 2)
        th = max(w.get("thickness", 100.0), 40.0)
        meshes.append(_box_mesh(center, (length, th, h), angle, [0.0, 0.75, 1.0]))
    return meshes


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
    """Pilarit umpinaisina laatikkoina."""
    meshes = []
    for c in model.get("columns", []):
        x, y = c["location"]; z0 = c["base_z"]; h = c["height"]
        pr = c["profile"]
        center = (x, y, z0 + h / 2)
        meshes.append(_box_mesh(center, (pr["width"], pr["depth"], h), 0.0, [1.0, 0.8, 0.0]))
    return meshes


def beam_geoms(model):
    """Palkit umpinaisina laatikkoina akselin suunnassa."""
    meshes = []
    for b in model.get("beams", []):
        a, c = np.array(b["axis"][0], float), np.array(b["axis"][1], float)
        d = c - a
        length = float(np.linalg.norm(d))
        if length < 1:
            continue
        angle = float(np.arctan2(d[1], d[0]))
        center = tuple((a + c) / 2)
        pr = b["profile"]
        meshes.append(_box_mesh(center, (length, pr["width"], pr["height"]), angle, [0.1, 0.85, 0.2]))
    return meshes


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
    geoms += wall_geoms(model)
    geoms += column_geoms(model)
    geoms += beam_geoms(model)
    op = opening_geoms(model, wall_by_id)
    if op is not None:
        geoms.append(op)
    print(f"malli: {len(model['walls'])} seinaa, {len(model.get('openings', []))} aukkoa, "
          f"{len(model.get('columns', []))} pilaria, {len(model.get('beams', []))} palkkia")
    o3d.visualization.draw_geometries(geoms, window_name="scan2bim navigointi", width=1600, height=1000)


if __name__ == "__main__":
    main()

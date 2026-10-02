"""Kirjoita Rohbau-scenejen cloud.ply float32-muodossa (puolet float64:n koosta).

coord.npy on float32, joten float64-PLY ei sisällä yhtään enempää tietoa.
Jokainen muunnos tarkistetaan: open3d:n lukemien pisteiden on oltava bitilleen
samat kuin vanhassa tiedostossa, muuten vanha jätetään paikalleen.

Kaytto: _ply_float32.py [scene_dir ...]   (oletus: kaikki data/_rohbau/site_*/scene_*)
"""
import sys
from pathlib import Path

import numpy as np
import open3d as o3d


def write_ply32(path: Path, pts: np.ndarray) -> None:
    pts = np.ascontiguousarray(pts, dtype="<f4")
    header = ("ply\nformat binary_little_endian 1.0\n"
              f"element vertex {len(pts)}\nproperty float x\nproperty float y\nproperty float z\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(pts.tobytes())


dirs = [Path(a) for a in sys.argv[1:]] or sorted(Path("data/_rohbau").glob("site_*/scene_*"))
saved = 0
for sc in dirs:
    ply = sc / "cloud.ply"
    if not ply.exists():
        continue
    old = np.asarray(o3d.io.read_point_cloud(str(ply)).points)
    if old.dtype == np.float64 and np.array_equal(old.astype(np.float32).astype(np.float64), old) is False:
        print(sc.name, "SKIP: ei float32-esitettävä")
        continue
    tmp = ply.with_suffix(".tmp.ply")
    write_ply32(tmp, np.load(sc / "coord.npy"))
    new = np.asarray(o3d.io.read_point_cloud(str(tmp)).points)
    if new.shape != old.shape or not np.array_equal(new, old):
        tmp.unlink()
        print(sc.name, "SKIP: pisteet eroavat")
        continue
    before = ply.stat().st_size
    tmp.replace(ply)
    saved += before - ply.stat().st_size
    print(f"{sc.name} ok {before / 1e6:.0f} -> {ply.stat().st_size / 1e6:.0f} MB", flush=True)
print(f"saasto {saved / 1e9:.1f} Gt")

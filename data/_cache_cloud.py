from pathlib import Path
import open3d as o3d, numpy as np
from scan2bim.core.geometry.loader import load_point_cloud
from _paths import DATA, DOWNLOADS  # portable dev-tool paths
apt = Path(str(DOWNLOADS / "raw_scans_apartment/apartment"))
merged = o3d.geometry.PointCloud()
for p in sorted(apt.glob("scan_*.ply")):
    c = load_point_cloud(p)
    c.normals = o3d.utility.Vector3dVector()
    c.colors = o3d.utility.Vector3dVector()
    c = c.voxel_down_sample(12.0)
    merged += c
    print(p.name, len(merged.points), flush=True)
merged = merged.voxel_down_sample(12.0)
out = Path(str(DATA / "_cache_apt.ply"))
o3d.io.write_point_cloud(str(out), merged)
print("CACHE", len(merged.points), "pts ->", out, f"{out.stat().st_size/1e6:.0f}MB")

from pathlib import Path
import numpy as np, open3d as o3d

apt = Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")
out = Path(r"C:\Users\lauri\scan2bim\reference\Cloud2BIM\output_xyz\apartment.xyz")
VOX = 0.015  # m (raaka PLY on jo metreissä)
total = 0
with open(out, "w") as f:
    for p in sorted(apt.glob("scan_*.ply")):
        pc = o3d.io.read_point_cloud(str(p)).voxel_down_sample(VOX)
        pts = np.asarray(pc.points)
        np.savetxt(f, pts, fmt="%.4f")
        total += len(pts)
        print(f"{p.name}: {len(pts):,} (cum {total:,})", flush=True)
print(f"DONE {total:,} -> {out}  ({out.stat().st_size/1e6:.0f} MB)")

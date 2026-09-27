"""Tallenna seinäkaista TÄYDELLÄ resalla 1.5mm tarkkuusmittausta varten (kerran)."""
from pathlib import Path
import open3d as o3d, numpy as np
from ordinate.core.geometry.loader import load_point_cloud
from _paths import DATA, DOWNLOADS  # portable dev-tool paths
apt=Path(str(DOWNLOADS / "raw_scans_apartment/apartment"))
# määritä lattia/katto ensin yhdestä skannista
c0=load_point_cloud(sorted(apt.glob('scan_*.ply'))[0])
z=np.asarray(c0.points)[:,2]; zmin,zmax=z.min(),z.max()
lo,hi=zmin+0.35*(zmax-zmin), zmin+0.65*(zmax-zmin)  # keskikaista, vähän kalusteita
merged=o3d.geometry.PointCloud()
for p in sorted(apt.glob('scan_*.ply')):
    c=load_point_cloud(p); c.normals=o3d.utility.Vector3dVector(); c.colors=o3d.utility.Vector3dVector()
    pts=np.asarray(c.points); m=(pts[:,2]>=lo)&(pts[:,2]<=hi)
    merged+=c.select_by_index(np.where(m)[0])
    print(p.name, len(merged.points), flush=True)
out=Path(str(DATA / "_qa_band.ply"))
o3d.io.write_point_cloud(str(out), merged)
print("QA-BAND", len(merged.points), "pts (täysi resa) ->", out, f"{out.stat().st_size/1e6:.0f}MB")

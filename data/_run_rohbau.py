"""Aja contour-pipeline Rohbau3D:lla (kalustamaton runko + per-piste GT).

Kaytto: _run_rohbau.py <site> [scene ...]     esim. _run_rohbau.py site_07
        ilman scene-argumentteja ajetaan KAIKKI scenet yhtena kohteena.
"""
import sys, json
from pathlib import Path
import numpy as np
import open3d as o3d
from shapely.geometry import Polygon

from scan2bim.core.pipeline import Pipeline, PipelineConfig
from _paths import DATA, OUTPUT  # portable dev-tool paths

D = Path(str(DATA / "_rohbau"))
site = sys.argv[1] if len(sys.argv) > 1 else "site_07"
scenes = sys.argv[2:] or [p.name for p in sorted((D / site).iterdir()) if p.is_dir()]

plys = []
for sc in scenes:
    ply = D / site / sc / "cloud.ply"
    if not ply.exists():
        P = np.load(D / site / sc / "coord.npy").astype(np.float64)
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(P)
        o3d.io.write_point_cloud(str(ply), pc)
        print(f"kirjoitettu {ply.name} {len(P):,} pistetta (metreja)", flush=True)
    plys.append(ply)

tag = site if len(scenes) > 1 else f"{site}_{scenes[0]}"
out = Path(str(OUTPUT / f"_rohbau_{tag}"))
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=True,
                     export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
models = Pipeline(cfg).run_floors(plys, out)
print(f"\n=== {tag}: {len(models)} kerrosta")
for i, m in enumerate(models):
    tot = sum(Polygon([(float(x), float(y)) for x, y in s.boundary]).area
              for s in m.spaces if len(s.boundary) >= 3) / 1e6
    print(f"  floor_{i:02d}: walls={len(m.walls)} "
          f"(perim={sum(1 for w in m.walls if w.source.method=='floorplan')}) "
          f"slabs={len(m.slabs)} spaces={len(m.spaces)} ala={tot:.1f} m2 "
          f"cols={len(m.columns)} beams={len(m.beams)} "
          f"doors={sum(1 for o in m.openings if o.opening_type=='door')} "
          f"windows={sum(1 for o in m.openings if o.opening_type=='window')}")
    for s in m.slabs:
        print(f"      {s.slab_type} z={s.elevation:.0f} t={s.thickness:.0f}")

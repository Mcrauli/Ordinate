"""Aja Rohbau3D site_07 KAIKILLA asemilla + instrumentoi _vertical_mask omilla
parametreillaan (viipalemaara, tarvittava maara, vcount-jakauma)."""
import sys
from pathlib import Path
import numpy as np
import open3d as o3d
from shapely.geometry import Polygon

import scan2bim.core.segmentation.wall_contour as WC

_orig = WC.WallDetectorContour._vertical_mask


def traced(self, clear, floor_z, ceil_z):
    z0 = floor_z + WC._VSLICE_BOTTOM
    z1 = ceil_z - WC._VSLICE_TOP
    n_sl = len(np.arange(z0, z1 + WC._VSLICE_STEP, WC._VSLICE_STEP)) - 1
    need = max(2, int(round(WC._VSLICE_FRAC * n_sl)))
    print(f"  [vmask] lattia={floor_z:.0f} katto={ceil_z:.0f} span={ceil_z-floor_z:.0f}mm "
          f"viipaleita={n_sl} tarvitaan={need} ({need*WC._VSLICE_STEP:.0f}mm jatkuvuutta) "
          f"pixel={self.pixel_size:.0f}mm", flush=True)
    binary, x_min, y_min = _orig(self, clear, floor_z, ceil_z)

    # sama vcount uudestaan raportointia varten (halpa: sama pilvi)
    xy, z = clear[:, :2], clear[:, 2]
    cols = max(int((xy[:, 0].max() - x_min) / self.pixel_size) + 1, 1)
    rows = max(int((xy[:, 1].max() - y_min) / self.pixel_size) + 1, 1)
    xr = [x_min, x_min + cols * self.pixel_size]
    yr = [y_min, y_min + rows * self.pixel_size]
    edges = np.arange(z0, z1 + WC._VSLICE_STEP, WC._VSLICE_STEP)
    vcount = np.zeros((rows, cols), dtype=np.int32)
    for k in range(len(edges) - 1):
        m = (z >= edges[k]) & (z < edges[k + 1])
        if int(m.sum()) < 10:
            continue
        g, _, _ = np.histogram2d(xy[m, 0], xy[m, 1], bins=[cols, rows], range=[xr, yr])
        vcount += (g.T >= WC._VSLICE_MIN_PER).astype(np.int32)
    occ = vcount[vcount > 0]
    if len(occ):
        qs = np.percentile(occ, [50, 75, 90, 95, 99])
        print(f"  [vmask] pikseleita>0: {len(occ):,}  vcount p50={qs[0]:.0f} p75={qs[1]:.0f} "
              f"p90={qs[2]:.0f} p95={qs[3]:.0f} p99={qs[4]:.0f}  "
              f"lapaisi={int((occ>=need).sum()):,} ({100*(occ>=need).mean():.1f}%)", flush=True)
        for frac in (0.20, 0.30, 0.40, 0.55):
            nd = max(2, int(round(frac * n_sl)))
            print(f"      jos FRAC={frac:.2f} (need={nd}): lapaisisi "
                  f"{int((occ>=nd).sum()):,} pikselia ({100*(occ>=nd).mean():.1f}%)", flush=True)
    print(f"  [vmask] maskipikselia={int((binary>0).sum()):,}", flush=True)
    return binary, x_min, y_min


WC.WallDetectorContour._vertical_mask = traced

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

D = Path(r"C:\Users\lauri\scan2bim\data\_rohbau\site_07")
plys = []
for sc in sorted(p for p in D.iterdir() if p.is_dir()):
    ply = sc / "cloud.ply"
    if not ply.exists():
        P = np.load(sc / "coord.npy").astype(np.float64)
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(P)
        o3d.io.write_point_cloud(str(ply), pc)
        print("kirjoitettu", ply.name, len(P), flush=True)
    plys.append(ply)

out = Path(r"C:\Users\lauri\scan2bim\data\output\_rohbau_site07_all")
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=True,
                     export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
models = Pipeline(cfg).run_floors(plys, out)
print(f"\n=== site_07 kaikki {len(plys)} asemaa: {len(models)} kerrosta")
for i, m in enumerate(models):
    tot = sum(Polygon([(float(x), float(y)) for x, y in s.boundary]).area
              for s in m.spaces if len(s.boundary) >= 3) / 1e6
    print(f"  floor_{i:02d}: walls={len(m.walls)} "
          f"(perim={sum(1 for w in m.walls if w.source.method=='floorplan')}) "
          f"spaces={len(m.spaces)} ala={tot:.1f} m2 cols={len(m.columns)} beams={len(m.beams)} "
          f"doors={sum(1 for o in m.openings if o.opening_type=='door')} "
          f"windows={sum(1 for o in m.openings if o.opening_type=='window')}")

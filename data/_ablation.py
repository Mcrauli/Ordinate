"""Ablaatio: mitka viidesta muutoksesta ansaitsevat paikkansa.
Kaytto: _ablation.py <variantti> <data...>
variantit: full | nocut | noadopt | nocut_noadopt
"""
import sys
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon

import scan2bim.core.segmentation.slab_detector as SD
import scan2bim.core.semantics.perimeter as PM

variant = sys.argv[1]
if variant in ("nocut", "nocut_noadopt"):
    SD._cut_walls = lambda grid, walls: grid
if variant in ("noadopt", "nocut_noadopt"):
    PM._adopt_measured_line = lambda *a, **k: None

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402
from _paths import DOWNLOADS, OUTPUT  # portable dev-tool paths

SETS = {
    "apt": sorted(Path(str(DOWNLOADS / "raw_scans_apartment/apartment")).glob("scan_*.ply")),
    "apt2": [Path(str(DOWNLOADS / "aligned_low_apartment/apt.ply"))],
    "bedroom": [Path(str(DOWNLOADS / "aligned_low_bedroom/bedroom.ply"))],
    "garage": [Path(str(DOWNLOADS / "gargage.e57"))],
}
for name in sys.argv[2:]:
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False,
                         semantic_filter_mode="pointnet")
    out = Path(str(OUTPUT / f"_abl_{variant}_{name}"))
    for m in Pipeline(cfg).run_floors(SETS[name], out):
        tot = sum(Polygon([(float(x), float(y)) for x, y in s.boundary]).area
                  for s in m.spaces if len(s.boundary) >= 3) / 1e6
        perim = [w for w in m.walls if w.source.method == "floorplan"]
        print(f"ABL {variant:14s} {name:8s} walls={len(m.walls):3d} perim={len(perim)} "
              f"spaces={len(m.spaces)} ala={tot:6.2f} m2 "
              f"doors={sum(1 for o in m.openings if o.opening_type=='door')} "
              f"windows={sum(1 for o in m.openings if o.opening_type=='window')} "
              f"maxT={max((w.thickness for w in m.walls), default=0):.0f}", flush=True)
        for w in perim:
            L = float(np.linalg.norm(np.array(w.axis[1]) - np.array(w.axis[0])))
            print(f"      perim {w.id} L={L:.0f} t={w.thickness:.0f}", flush=True)

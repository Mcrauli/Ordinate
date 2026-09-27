from pathlib import Path
from ordinate.core.pipeline import Pipeline, PipelineConfig
from _paths import DOWNLOADS, OUTPUT  # portable dev-tool paths
apt = Path(str(DOWNLOADS / "raw_scans_apartment/apartment"))
paths = sorted(apt.glob("scan_*.ply"))
cfg = PipelineConfig(detector="floorplan", auto_voxel=True,
                     export_ifc=True, export_dxf=False, export_qa=False)
out = Path(str(OUTPUT / "_floorplan"))
models = Pipeline(cfg).run_floors(paths, out)
for m in models:
    print(f"walls={len(m.walls)} doors={sum(1 for o in m.openings if o.opening_type=='door')} "
          f"spaces={len(m.spaces)} columns={len(m.columns)}")

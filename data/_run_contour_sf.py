from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig
apt = Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")
paths = sorted(apt.glob("scan_*.ply"))
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=True,
                     export_dxf=False, export_qa=False, semantic_filter=True)
out = Path(r"C:\Users\lauri\scan2bim\data\output\_contour_sf_ifc")
models = Pipeline(cfg).run_floors(paths, out)
for m in models:
    print(f"walls={len(m.walls)} spaces={len(m.spaces)} doors={sum(1 for o in m.openings if o.opening_type=='door')}")

import time
from pathlib import Path
from ordinate.core.pipeline import Pipeline, PipelineConfig
from _paths import DOWNLOADS, OUTPUT  # portable dev-tool paths
apt = Path(str(DOWNLOADS / "raw_scans_apartment/apartment"))
paths = sorted(apt.glob("scan_*.ply"))
for icp in (True,):  # ilman-ICP-tulos on jo _contour_ifc (23 walls 4 spaces)
    t0=time.time()
    cfg = PipelineConfig(detector="contour", auto_voxel=True, icp_refine=icp,
                         export_ifc=False, export_dxf=False, export_qa=False)
    out = Path(str(OUTPUT / f"_icp_{icp}"))
    models = Pipeline(cfg).run_floors(paths, out)
    dt=time.time()-t0
    for m in models:
        print(f"ICP={icp}: walls={len(m.walls)} spaces={len(m.spaces)} "
              f"doors={sum(1 for o in m.openings if o.opening_type=='door')}  time={dt:.0f}s")

import time
from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig
apt = Path(r"C:\Users\lauri\Downloads\raw_scans_apartment\apartment")
paths = sorted(apt.glob("scan_*.ply"))
for icp in (True,):  # ilman-ICP-tulos on jo _contour_ifc (23 walls 4 spaces)
    t0=time.time()
    cfg = PipelineConfig(detector="contour", auto_voxel=True, icp_refine=icp,
                         export_ifc=False, export_dxf=False, export_qa=False)
    out = Path(rf"C:\Users\lauri\scan2bim\data\output\_icp_{icp}")
    models = Pipeline(cfg).run_floors(paths, out)
    dt=time.time()-t0
    for m in models:
        print(f"ICP={icp}: walls={len(m.walls)} spaces={len(m.spaces)} "
              f"doors={sum(1 for o in m.openings if o.opening_type=='door')}  time={dt:.0f}s")

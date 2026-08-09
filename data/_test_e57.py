import time
from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig
from _paths import DOWNLOADS, OUTPUT  # portable dev-tool paths
for name in ["gargage.e57"]:
    p=Path(str(DOWNLOADS / f"{name}"))
    if not p.exists(): print("puuttuu",p); continue
    t0=time.time()
    cfg=PipelineConfig(detector="contour",auto_voxel=True,export_ifc=True,export_dxf=False,export_qa=False)
    out=Path(str(OUTPUT / f"_e57_{p.stem}"))
    try:
        models=Pipeline(cfg).run_floors([p],out)
        for m in models:
            print(f"{name}: walls={len(m.walls)} spaces={len(m.spaces)} "
                  f"doors={sum(1 for o in m.openings if o.opening_type=='door')} "
                  f"cols={len(m.columns)}  {time.time()-t0:.0f}s  IFC={out/'building.ifc'}")
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f"{name}: KAATUI {type(e).__name__}: {e}")

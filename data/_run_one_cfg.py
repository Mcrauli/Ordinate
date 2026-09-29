"""_run_one.py + moduulivakioiden korvaus: _run_one_cfg.py <pilvi> <hakemisto> [MOD:NIMI=arvo ...]"""
import ast
import importlib
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    for s in sys.argv[3:]:
        mod, rest = s.split(":", 1)
        name, val = rest.split("=", 1)
        setattr(importlib.import_module(mod), name, ast.literal_eval(val))
    from ordinate.core.pipeline import Pipeline, PipelineConfig

    t = time.time()
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
    models = Pipeline(cfg).run_floors([Path(sys.argv[1])], Path(sys.argv[2]))
    print(f"aika {time.time() - t:.0f} kerroksia {len(models)}")

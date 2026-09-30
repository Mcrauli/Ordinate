"""_run_one.py + asetukset: _run_one_cfg.py <pilvi> <hakemisto> [MOD:NIMI=arvo ...] [detector=nimi]

detector=nimi pakottaa detektorin (valintakisa ohitetaan)."""
import ast
import importlib
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    det = None
    for s in sys.argv[3:]:
        if s.startswith("detector="):
            det = s.split("=", 1)[1]
            continue
        mod, rest = s.split(":", 1)
        name, val = rest.split("=", 1)
        setattr(importlib.import_module(mod), name, ast.literal_eval(val))
    from ordinate.core import pipeline as PL

    if det:
        orig = PL.Pipeline._best_detector
        PL.Pipeline._best_detector = lambda self, c, names: orig(self, c, [det])
    t = time.time()
    cfg = PL.PipelineConfig(detector=det or "contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
    models = PL.Pipeline(cfg).run_floors([Path(sys.argv[1])], Path(sys.argv[2]))
    print(f"aika {time.time() - t:.0f} kerroksia {len(models)}")

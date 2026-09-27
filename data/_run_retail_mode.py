"""Aja retail-pilvi valitulla semantic_filter_mode:lla. Arg1=ply, arg2=out, arg3=mode."""
import sys
from pathlib import Path
from ordinate.core.pipeline import Pipeline, PipelineConfig

ply, out, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
cfg = PipelineConfig(detector="ransac", export_ifc=False, export_dxf=False,
                     semantic_filter_mode=mode)
m = Pipeline(cfg, progress=print).run(ply, out)
print("WALLS", len(m.walls), "COLS", len(m.columns), "SPACES", len(m.spaces))

"""Aja retail-pilvi valitulla detektorilla + suodatinmoodilla.
argv: ply out detector mode"""
import sys
from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig

ply, out, detector, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
cfg = PipelineConfig(detector=detector, export_ifc=False, export_dxf=False,
                     semantic_filter_mode=mode)
m = Pipeline(cfg, progress=print).run(ply, out)
print("WALLS", len(m.walls), "COLS", len(m.columns), "SPACES", len(m.spaces))

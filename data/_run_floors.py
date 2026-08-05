"""Aja skanni run_floors-polulla (täyttää skanneri­origot → okkluusio + skannausalue).
argv: src out detector mode"""
import sys, json
from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig

src, out, detector, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
cfg = PipelineConfig(detector=detector, semantic_filter_mode=mode,
                     export_ifc=False, export_dxf=False)
models = Pipeline(cfg, progress=print).run_floors([src], out)
m = models[0]
print("WALLS", len(m.walls), "OPEN", len(m.openings), "COLS", len(m.columns),
      "BEAMS", len(m.beams), "SPACES", len(m.spaces))

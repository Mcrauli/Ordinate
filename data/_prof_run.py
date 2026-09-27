"""cProfile yhdelle aineistolle: mihin aika oikeasti menee.

AGENTS.md: nopeusvaite on mitattava, ei arvattava. Tama ajaa saman
kokoonpanon kuin `_run_one.py` cProfilen alla ja tulostaa raskaimmat
funktiot kumulatiivisesti seka omalla ajallaan.

Ajo: _prof_run.py <pilvi.ply> <hakemisto> [rivit]
"""
import cProfile
import pstats
import sys
from pathlib import Path

from ordinate.core.pipeline import Pipeline, PipelineConfig

cloud = Path(sys.argv[1])
out = Path(sys.argv[2])
rows = int(sys.argv[3]) if len(sys.argv) > 3 else 35
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                     export_dxf=False, export_qa=False,
                     semantic_filter_mode="pointnet")

pr = cProfile.Profile()
pr.enable()
models = Pipeline(cfg).run_floors([cloud], out)
pr.disable()
for i, m in enumerate(models):
    print(f"  floor_{i:02d}: walls={len(m.walls)} slabs={len(m.slabs)}")

pr.dump_stats(str(out / "_prof.out"))
st = pstats.Stats(pr)
print("\n=== KUMULATIIVINEN ===")
st.sort_stats("cumulative").print_stats(rows)
print("\n=== OMA AIKA ===")
st.sort_stats("tottime").print_stats(rows)

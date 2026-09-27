from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig
SRC=Path(r"C:\Users\lauri\Downloads\aligned_low_apartment\apt.ply")
cfg=PipelineConfig(detector="contour",auto_voxel=True,export_ifc=True,export_dxf=False,export_qa=False,semantic_filter_mode="pointnet")
out=Path(r"C:\Users\lauri\scan2bim\data\output\_apt2_sf_ifc")
models=Pipeline(cfg).run_floors([SRC],out)
import json
m=json.loads((out/"floor_00"/"model.json").read_text())
print("RESULT walls=%d spaces=%d doors=%d windows=%d"%(len(m["walls"]),len(m.get("spaces",[])),sum(1 for o in m.get("openings",[]) if o["opening_type"]=="door"),sum(1 for o in m.get("openings",[]) if o["opening_type"]=="window")))
for o in m.get("openings",[]): print("  %s wall=%s w=%.0f"%(o["opening_type"],o["wall_id"],o["width"]))

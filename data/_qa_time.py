"""QA:n kaksi osaa erikseen: pistetason poikkeama (raycast) vs pintatarkkuus."""
import sys, time
from pathlib import Path
import open3d as o3d
from ordinate.core.qa import deviation as dv
from ordinate.schemas.model import StructuralModel
import json

out = Path(sys.argv[1]); cloud_path = Path(sys.argv[2])
m = StructuralModel.model_validate(json.loads(
    sorted(out.glob("floor_*/model.json"))[0].read_text(encoding="utf-8")))
pc = o3d.io.read_point_cloud(str(cloud_path))
print(f"{len(pc.points):,} pistetta, {len(m.walls)} seinaa")
ifc = sorted(out.glob("floor_*/*.ifc")) + sorted(out.glob("*.ifc"))
t = time.time(); r = dv.wall_surface_accuracy(m, pc)
print(f"wall_surface_accuracy {time.time()-t:7.1f}s  ({len(r)} seinaa)")
if ifc:
    t = time.time(); dv.model_deviation(pc, ifc[0])
    print(f"model_deviation       {time.time()-t:7.1f}s  ({ifc[0].name})")

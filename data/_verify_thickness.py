from pathlib import Path
from ordinate.core.pipeline import Pipeline, PipelineConfig
from _paths import DOWNLOADS, OUTPUT  # portable dev-tool paths

cfg = PipelineConfig(detector="normals", auto_voxel=False, voxel_size=12.0,
                     export_ifc=False, export_dxf=False, export_qa=False)
src = Path(str(DOWNLOADS / "raw_scans_apartment/apartment/scan_06.ply"))
out = Path(str(OUTPUT / "_verify"))
m = Pipeline(cfg).run([src], out)
print("\n=== THICKNESSES (mm) ===")
for w in sorted(m.walls, key=lambda w: -w.confidence):
    p0,p1 = w.axis[0], w.axis[1]
    ln = ((p1[0]-p0[0])**2+(p1[1]-p0[1])**2)**0.5
    print(f"{w.id:10s} t={w.thickness:6.1f}  len={ln:6.0f}  conf={w.confidence:.2f}")
print(f"\nwalls={len(m.walls)} openings={len(m.openings)} "
      f"(doors={sum(1 for o in m.openings if o.opening_type=='door')}, "
      f"windows={sum(1 for o in m.openings if o.opening_type=='window')}) "
      f"columns={len(m.columns)} slabs={len(m.slabs)}")

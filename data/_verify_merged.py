from pathlib import Path
from ordinate.core.pipeline import Pipeline, PipelineConfig
from _paths import DOWNLOADS, OUTPUT  # portable dev-tool paths

apt = Path(str(DOWNLOADS / "raw_scans_apartment/apartment"))
paths = sorted(apt.glob("scan_*.ply"))
cfg = PipelineConfig(detector="normals", auto_voxel=True,
                     export_ifc=True, export_dxf=False, export_qa=False)
out = Path(str(OUTPUT / "_merged"))
models = Pipeline(cfg).run_floors(paths, out)
for m in models:
    print(f"\n=== floor {m.metadata.floor_index} ===")
    for w in sorted(m.walls, key=lambda w:-w.confidence):
        p0,p1=w.axis; ln=((p1[0]-p0[0])**2+(p1[1]-p0[1])**2)**0.5
        print(f"  {w.id:10s} t={w.thickness:6.1f} len={ln:6.0f} c={w.confidence:.2f}")
    print(f"  walls={len(m.walls)} doors={sum(1 for o in m.openings if o.opening_type=='door')} "
          f"windows={sum(1 for o in m.openings if o.opening_type=='window')} "
          f"spaces={len(m.spaces)} columns={len(m.columns)}")

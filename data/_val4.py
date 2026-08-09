"""Validoi 4 datalla ettei korjaus regressoi: kontuurin validius + ala,
perimetriseinien pistetuki, seinamaarat."""
import sys
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon

from scan2bim.core.pipeline import Pipeline, PipelineConfig
from _paths import DATA, DOWNLOADS, OUTPUT  # portable dev-tool paths

SETS = {
    "apt2":    [Path(str(DOWNLOADS / "aligned_low_apartment/apt.ply"))],
    "bedroom": [Path(str(DOWNLOADS / "aligned_low_bedroom/bedroom.ply"))],
    "garage":  [Path(str(DOWNLOADS / "gargage.e57"))],
    "3dses":   [Path(str(DATA / "_3dses/_3dses_cloud.ply"))],
}
names = sys.argv[1:] or list(SETS)

for name in names:
    paths = [p for p in SETS[name] if p.exists()]
    if not paths:
        print(f"\n### {name}: puuttuu, ohitetaan"); continue
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False,
                         semantic_filter_mode="pointnet")
    out = Path(str(OUTPUT / f"_val_{name}"))
    try:
        models = Pipeline(cfg).run_floors(paths, out)
    except Exception as e:
        print(f"\n### {name}: KAATUI {type(e).__name__}: {e}"); continue
    print(f"\n### {name}")
    for i, m in enumerate(models):
        fp = [w for w in m.walls if w.source.method == "floorplan"]
        print(f"  floor_{i}: walls={len(m.walls)} (floorplan={len(fp)}) "
              f"spaces={len(m.spaces)} slabs={len(m.slabs)} "
              f"doors={sum(1 for o in m.openings if o.opening_type=='door')} "
              f"windows={sum(1 for o in m.openings if o.opening_type=='window')}")
        for s in m.spaces:
            b = s.boundary
            if len(b) >= 3:
                p = Polygon([(float(x), float(y)) for x, y in b])
                print(f"    {s.id}: ala={p.area/1e6:6.2f} m2 valid={p.is_valid}")
        for w in fp:
            L = float(np.linalg.norm(np.array(w.axis[1]) - np.array(w.axis[0])))
            print(f"    {w.id}: L={L:.0f} t={w.thickness:.0f} conf={w.confidence:.2f}")

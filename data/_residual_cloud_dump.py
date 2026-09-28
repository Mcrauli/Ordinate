"""Kellarin tuotantoajo joka tallentaa jaannoshaun SYOTEPILVEN (viimeinen
kutsu) ja mallin seinat sen hetkella. Kaytto: _residual_cloud_dump.py <out_dir>"""
import json
import sys
from pathlib import Path

import numpy as np

if __name__ == "__main__":
    import psutil
    psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    import ordinate.core.semantics.residual_walls as RW
    from ordinate.core.pipeline import Pipeline, PipelineConfig
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    fn = RW.find_residual_walls
    calls = []

    def spy(walls, cloud, floor_z, ceiling_z, split_wide=False):
        k = len(calls)
        np.savez_compressed(out / f"residual_in_{k}.npz", pts=np.asarray(cloud.points, dtype=np.float32),
                            fz=floor_z, cz=ceiling_z, split=split_wide)
        (out / f"residual_walls_{k}.json").write_text(json.dumps([w.model_dump() for w in walls]), encoding="utf-8")
        calls.append(k)
        return fn(walls, cloud, floor_z, ceiling_z, split_wide=split_wide)
    RW.find_residual_walls = spy
    files = sorted(Path("data/_kellari_nvme").glob("Kellari- Kellari 0*.e57"))
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False, export_dxf=False,
                         export_qa=False, semantic_filter_mode="pointnet")
    Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(files, out)

"""Kellarin tuotantoajo samoilla asetuksilla kuin GUI (36 numeroitua skannia).
Kaytto: _kellari_run.py <out_dir>"""
import sys
from pathlib import Path

if __name__ == "__main__":
    import psutil
    psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    from ordinate.core.pipeline import Pipeline, PipelineConfig
    files = sorted(Path("data/_kellari_nvme").glob("Kellari- Kellari 0*.e57"))
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False, export_dxf=False,
                         export_qa=False, semantic_filter_mode="pointnet")
    Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(files, Path(sys.argv[1]))

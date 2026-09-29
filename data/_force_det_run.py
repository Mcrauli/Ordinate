"""Aja putki pakotetulla detektorilla (valintakisa ohitetaan).

Kaytto: _force_det_run.py <detektori> <pilvi.ply> <out_dir>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

if __name__ == "__main__":
    from ordinate.core import pipeline as PL

    det, cloud, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    orig = PL.Pipeline._best_detector
    PL.Pipeline._best_detector = lambda self, c, names: orig(self, c, [det])
    cfg = PL.PipelineConfig(detector=det, auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    m = PL.Pipeline(cfg, progress=lambda s: None).run_floors([cloud], out)[0]
    print(f"{det} seinia {len(m.walls)}")

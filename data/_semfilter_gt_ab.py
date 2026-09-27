"""Poistaako semanttinen suodatin ne puuttuvat valiseinat?

Aiempi karsintakoe (`_prune_gt_probe.py`) kytki pois kaikki DETEKTION JALKEISET
karsinnat eika luku liikkunut. Mutta `_semantic_filter` ajetaan ENNEN
detektiota ja se poistaa PISTEITA: jos PointNet luokittelee 2-4 m valiseinan
kalusteeksi tai roinaksi, detektori ei koskaan nae sita eika mikaan myohempi
portti voi palauttaa sita.

Tama ajaa saman scenen suodatin paalla ja pois, ja mittaa GT-instanssit.

Kaytto: _semfilter_gt_ab.py <scene_dir> <out_root>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))


def _inst(model: Path, scene: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(HERE / "_wall_inst_qa.py"), str(model),
         str(scene / "coord.npy"), str(scene / "class.npy"),
         str(scene / "instance.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    keep = [ln.strip() for ln in r.stdout.splitlines()
            if "INSTANSSIKATTAVUUS" in ln or ln.strip().startswith(("yli 4", "2-4", "1-2"))]
    return " | ".join(keep)


def main(scene_dir: str, out_root: str) -> None:
    from ordinate.core import pipeline as PL

    scene = Path(scene_dir)
    for mode in ("pointnet", "off"):
        out = Path(out_root) / mode
        cfg = PL.PipelineConfig(detector="contour", auto_voxel=True,
                                export_ifc=False, export_dxf=False, export_qa=False,
                                semantic_filter_mode=mode)
        m = PL.Pipeline(cfg, progress=lambda s: None).run_floors(
            [scene / "cloud.ply"], out)[0]
        mj = out / "floor_00" / "model.json"
        print(f"suodatin={mode:8s} seinia {len(m.walls):3d}")
        print(f"  {_inst(mj, scene)}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])

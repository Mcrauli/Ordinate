"""Mita jaannosseinahaku MAKSAA ja TUO kalustetayteisessa myymalassa?

Keilatussa myymalassa malli antaa 52 seinaa kymmenelle GT-seinalle, ja niista
35 on `find_residual_walls`in tuotosta — 22 alle 2 m tynkia. Rohbaun rungossa
sama haku dokumentoidusti NOSTAA kattavuutta kaikilla viidella scenella
hintaan 0.002-0.016 tarkkuutta. Sama moduuli kayttaytyy siis aineistotyypin
mukaan taysin eri tavalla, ja se on mitattava eika paateltava.

Ajaa putken kahdesti: normaalisti ja haku identiteettina.

Kaytto: _residual_ab.py <cloud.ply> <out_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(cloud: str, out: str) -> None:
    from ordinate.core import pipeline as PL
    from ordinate.core.semantics import residual_walls as RW

    RW.find_residual_walls = lambda *a, **kw: []
    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    models = PL.Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(
        [Path(cloud)], Path(out))
    for i, m in enumerate(models):
        print(f"  floor_{i:02d}: walls={len(m.walls)} cols={len(m.columns)} "
              f"beams={len(m.beams)} openings={len(m.openings)}")


if __name__ == "__main__":
    main(*sys.argv[1:])

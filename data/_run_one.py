"""Aja putki yhdelle pilvelle samalla kokoonpanolla kuin `_run_rohbau.py`.

Kokoonpano on kopio tarkoituksella: jos vertailuajo käyttäisi eri asetuksia,
mitattu ero ei olisi sen muuttujan ero jota tutkitaan.

Ajo: _run_one.py <pilvi.ply> <hakemisto>
"""
import sys
from pathlib import Path

from scan2bim.core.pipeline import Pipeline, PipelineConfig

# Monen tiedoston ajo lukee tiedostot prosessipoolissa, ja Windowsin
# spawn importtaa lapsessa __main__:in — ilman tätä vartijaa skripti
# käynnistäisi itsensä rekursiivisesti.
if __name__ == "__main__":
    cloud = Path(sys.argv[1])
    out = Path(sys.argv[2])
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
    models = Pipeline(cfg).run_floors([cloud], out)
    for i, m in enumerate(models):
        print(f"  floor_{i:02d}: walls={len(m.walls)} slabs={len(m.slabs)} "
              f"cols={len(m.columns)} beams={len(m.beams)} openings={len(m.openings)}")

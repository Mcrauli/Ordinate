"""Synnyttaako paiden leikkaus ne raot jotka estavat kollineaarisen sulautuksen?

Mitattu retail_l:n tuotantomallista: 36 seinaa 9 GT-seinalle, ja 27/29
"ylimaaraista" on 0-225 mm paassa GT-linjasta kulmaerolla 0.0°. Palasten
valissa on 21 rakoa joista 18 on TASMALLEEN 0.66 m — vakio, ei mittaus.
Raoissa on ~4900 pistetta seinapintaa, lahin pilari 11-35 m ja lahin GT-aukko
4.6 m, joten mikaan fysikaalinen ei katkaise seinaa siina.

Epailty: `_MAX_TRIM` on 300 mm per paa ja `_COLIN_GAP_MM` 450 mm. Kaksi
vierekkaista palasta, kumpikin leikattuna 300 mm jaetusta paasta, tekee 600 mm
raon jota sulautus ei enaa ylita. Ketjujarjestys tukee: trim ajetaan ENNEN
merge_collineariä.

Tama EI korjaa mitaan — se kytkee leikkauksen pois ja katsoo sulautuvatko
palaset. Jos sulautuvat, diagnoosi pitaa ja korjaus voidaan suunnitella.

Kaytto: _trim_ablation.py <pilvi.ply> <out_dir> [gt.json]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))


def main(cloud: str, out_dir: str, gt: str | None = None) -> None:
    from scan2bim.core import pipeline as PL

    PL._MAX_TRIM = 0.0                      # modulitason vakio
    if hasattr(PL, "_trim_endpoints"):
        orig = PL._trim_endpoints
        PL._trim_endpoints = lambda w, pts, index=None: w
        PL._trim_wall_endpoints = lambda walls, cloud: list(walls)
        print(f"  leikkaus kytketty pois ({orig.__name__} -> identiteetti)")

    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    out = Path(out_dir)
    m = PL.Pipeline(cfg, progress=lambda s: None).run_floors([Path(cloud)], out)[0]
    print(f"ilman leikkausta: {len(m.walls)} seinaa")
    if gt and Path(gt).exists():
        r = subprocess.run([sys.executable, str(HERE / "_retail_qa.py"), str(out), gt],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        for l in r.stdout.splitlines():
            if any(k in l for k in ("malli:", "loytyi", "hyllysta", "ylimaaraisia")):
                print("  " + l.strip())
    r = subprocess.run([sys.executable, str(HERE / "_wall_coverage_nogt.py"),
                        str(out / "floor_00" / "model.json"), cloud],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for l in r.stdout.splitlines():
        if l.startswith(("KATTAVUUS", "TARKKUUS")):
            print("  " + " ".join(l.split()))


if __name__ == "__main__":
    main(*sys.argv[1:])

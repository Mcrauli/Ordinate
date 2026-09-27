"""Valitaanko detektori mittarilla joka ei nae sita mita haetaan?

`_best_detector` valitsee detektorin maksimoimalla PISTEkattavuuden. Mitattu
tassa sessiossa: pistekattavuus on 0.759-0.920 samaan aikaan kun
INSTANSSIkattavuus on 0.409-0.673, ja koko ero on lyhyissa seinissa
(yli 4 m: 94 %, 2-4 m: 46 %, 1-2 m: 24 %). Perimetrilla on valtaosa pisteista,
joten pistekattavuus palkitsee perimetrin ja on lahes sokea valiseinille.

Jos eri detektorit ovat eri tavalla hyvia naissa kahdessa, valinta voi
systemaattisesti valita vaarin. Tama ajaa saman scenen kaikilla kolmella
detektorilla ja mittaa MOLEMMAT: piste- ja GT-instanssikattavuuden.

Jos histogram voittaa pisteissa mutta haviaa instansseissa, valintamittari on
vaara — ja se on korjattavissa ilman GT:ta, koska `_wall_inst_nogt.py` mittaa
instansseja pilvesta.

Kaytto: _detector_gt_ab.py <scene_dir> <out_root>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))


def _inst_cov(model: Path, scene: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(HERE / "_wall_inst_qa.py"), str(model),
         str(scene / "coord.npy"), str(scene / "class.npy"),
         str(scene / "instance.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for line in r.stdout.splitlines():
        if "INSTANSSIKATTAVUUS" in line or line.strip().startswith(("yli 4", "2-4", "1-2")):
            out.append(line.strip())
    return " | ".join(out)


def main(scene_dir: str, out_root: str) -> None:
    from ordinate.core import pipeline as PL

    scene = Path(scene_dir)
    orig = PL.Pipeline._best_detector
    for det in ("contour", "histogram", "normals"):
        out = Path(out_root) / det
        # Pakota valinta rajaamalla EHDOKASLISTA yhteen — muuten iso tila ajaa
        # oman mittauksensa ja valitsee itse. Tuotantokoodi ajetaan sellaisenaan.
        PL.Pipeline._best_detector = (
            lambda self, cloud, names, _d=det: orig(self, cloud, [_d]))
        cfg = PL.PipelineConfig(detector=det, auto_voxel=True, export_ifc=False,
                                export_dxf=False, export_qa=False,
                                semantic_filter_mode="pointnet")
        m = PL.Pipeline(cfg, progress=lambda s: None).run_floors([scene / "cloud.ply"], out)[0]
        mj = out / "floor_00" / "model.json"
        r = subprocess.run(
            [sys.executable, str(HERE / "_wall_coverage_nogt.py"), str(mj),
             str(scene / "cloud.ply")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        cov = pre = "?"
        for line in r.stdout.splitlines():
            if line.startswith("KATTAVUUS"):
                cov = line.split(":")[-1].strip()
            if line.startswith("TARKKUUS"):
                pre = line.split(":")[-1].strip()
        print(f"{det:10s} seinia {len(m.walls):3d}  pistekatt {cov}  tarkkuus {pre}")
        print(f"           {_inst_cov(mj, scene)}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])

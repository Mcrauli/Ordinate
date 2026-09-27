"""Puuttuvatko lyhyet seinat siksi ettei niita LOYDETA vai siksi etta ne KARSITAAN?

Rohbau3D-GT:n instanssikattavuus pituusluokittain (kaikki viisi scenea):
  yli 4 m   34/36 = 94 %
  2-4 m     41/89 = 46 %
  1-2 m      4/17 = 24 %
Pitkat loytyvat lahes aina, lyhyet joka toinen — ja ne ovat jalanjaljen SISALLA.

Kaksi mahdollista syyta, ja ne vaativat eri korjauksen:
  a) detektori ei tuota niita  -> portteja loysaamalla ei saa mitaan
  b) detektori tuottaa, karsinta poistaa -> portti on liian tiukka lyhyille

Tama ajaa saman scenen kahdesti: kerran normaalisti, kerran KAIKKI karsinnat
identiteetteina, ja mittaa instanssikattavuuden molemmista. Ero kertoo kumpi.

HUOM: karsinnaton malli EI ole ehdotus — se on diagnoosi. Karsinnat ovat
olemassa siksi etta ilman niita tarkkuus romahtaa; tama kertoo vain missa
puuttuvat seinat ovat.

Kaytto: _prune_gt_probe.py <scene_dir> <out_dir> [off|on]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))


def main(scene_dir: str, out_dir: str, mode: str = "off") -> None:
    from ordinate.core import pipeline as PL

    scene = Path(scene_dir)
    out = Path(out_dir)

    if mode == "off":
        from ordinate.core.qa import deviation as DEV
        from ordinate.core.semantics import contrast_prune as CP
        from ordinate.core.semantics import direction_prune as DP
        from ordinate.core.semantics import flatness_prune as FP
        from ordinate.core.semantics import overstretch as OS
        from ordinate.core.semantics import semantic_prune as SP
        from ordinate.core.semantics import wall_semantics as WS

        _none = lambda *a, **kw: []          # noqa: E731 — palauttaa "ei poistettu"
        _same = lambda walls, *a, **kw: walls  # noqa: E731
        DEV.prune_unsupported_walls = _none
        SP.prune_non_wall_surfaces = _none
        CP.prune_uncontrasted_walls = _none
        FP.prune_flatless_walls = _none
        DP.prune_offdirection_walls = _none
        OS.trim_overstretched_walls = _none
        WS.remove_dangling_walls = _same
        WS.filter_structural_walls = _same
        PL.filter_structural_walls = _same
        print("KARSINNAT POIS", flush=True)
    else:
        print("KARSINNAT PAALLA (viite)", flush=True)

    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    m = PL.Pipeline(cfg, progress=lambda s: print(s, flush=True)).run_floors(
        [scene / "cloud.ply"], out)[0]
    print(f"seinia mallissa {len(m.walls)}", flush=True)

    r = subprocess.run(
        [sys.executable, str(HERE / "_wall_inst_qa.py"),
         str(out / "floor_00" / "model.json"), str(scene / "coord.npy"),
         str(scene / "class.npy"), str(scene / "instance.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-1400:])


if __name__ == "__main__":
    main(*sys.argv[1:])

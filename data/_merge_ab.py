"""Auttaisiko PELKKA kollineaarinen sulautus isossa matalassa tilassa?

Nurkkakoneisto kytkettiin pois NELJANA NIPPUNA (`regularize_orthogonal`,
`snap_corners`, `close_open_corners`, `merge_collinear_walls`), koska nippu
mitattiin kokonaisuutena: kattavuus 0.194 -> 0.366. Kolme niista SIIRTAA
geometriaa — pakottavat suuntiin, venyttavat paita risteyksiin. Sulautus ei:
se yhdistaa patkia jotka ovat jo samalla linjalla ja ottaa OHUEMMAN paksuuden.

Kellarin seinien mediaanipituus on 1.8 m ja 142/240 on alle 2 m. Jos ne ovat
saman seinan palasia, sulautus parantaa mallia ilman etta mikaan liikkuu.
Jos ne ovat eri seinia, sulautus yhdistaa niita vaarin ja kattavuus laskee.
Kumpi, se on mitattava — ei paateltava.

Tama pakottaa nurkkareitityksen paalle mutta korvaa ne KOLME siirtavaa
funktiota identiteeteilla, jolloin ajossa on tasan yksi ero nykytilaan.

Kaytto: _merge_ab.py <pilvi.ply> <out_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(cloud: str, out_dir: str) -> None:
    from scan2bim.core import pipeline as PL
    from scan2bim.core.semantics import corner_snap as CS
    from scan2bim.core.semantics import orthogonal as OR

    src = Path(cloud)

    # Reititys paalle, mutta vain sulautus jaa voimaan.
    PL._CORNER_MIN_HEIGHT = 0.0
    _ident = lambda walls, *a, **kw: walls  # noqa: E731
    CS.snap_corners = _ident
    CS.close_open_corners = _ident
    OR.regularize_orthogonal = _ident
    PL.snap_corners = _ident
    PL.close_open_corners = _ident
    print("AJO: nurkkareititys paalla, vain merge_collinear_walls aktiivinen",
          flush=True)

    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    m = PL.Pipeline(cfg, progress=lambda s: print(s, flush=True)).run_floors(
        [src], Path(out_dir))[0]

    lens = [float(np.linalg.norm(np.asarray(w.axis[-1], float)
                                 - np.asarray(w.axis[0], float)))
            for w in m.walls if len(w.axis) > 1]
    print(f"\nVAIN SULAUTUS: {len(m.walls)} seinaa, {sum(lens)/1000:.0f} m, "
          f"mediaanipituus {np.median(lens)/1000:.1f} m")
    # Kattavuus ja tarkkuus mitataan SAMALLA skriptilla kuin matriisi, jotta
    # luvut ovat vertailukelpoisia — ei rinnakkaisella toteutuksella.
    print(f"aja mittari: _wall_coverage_nogt.py {out_dir}/floor_00/model.json {cloud}")


if __name__ == "__main__":
    main(*sys.argv[1:])

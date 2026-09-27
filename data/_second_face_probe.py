"""Keksiiko katvepintahaku seinia sinne missa niita ei ole?

Rohbaussa `find_hidden_walls` nostaa kattavuuden 0.792 -> 0.887, mutta siella
on GT. Muissa aineistoissa ei ole — siksi ainoa mitattava asia on VAARA
POSITIIVINEN: kalustetussa asunnossa tai kaupassa hyllyrivi tai kaappi on
seinan suuntainen pinta puolen metrin paassa, ja se EI ole seina.

Tulostaa jokaisesta aineistosta loydetyt katveseinat + niiden mitatun tuen ja
jatkuvuuden, jotta lisayksen voi arvioida ilman GT:ta.

Ajo: .venv/Scripts/python.exe data/_second_face_probe.py [nimi ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import DATA, OUTPUT  # noqa: E402

from ordinate.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

SETS = {
    "retail_s": DATA / "_retail_s.ply",
    "retail_l": DATA / "_retail_l.ply",
    "apt": DATA / "_apt_merged.ply",
    "3dses": DATA / "_3dses" / "_3dses_cloud.ply",
}


def main() -> None:
    names = sys.argv[1:] or list(SETS)
    for name in names:
        ply = Path(str(SETS[name]))
        if not ply.exists():
            print(f"{name}: PUUTTUU {ply}")
            continue
        cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                             export_dxf=False, export_qa=False)
        models = Pipeline(cfg).run_floors([ply], Path(str(OUTPUT / f"_2nd_{name}")))
        walls = [w for m in models for w in m.walls]
        new = [w for w in walls if w.source.method == "second_face"]
        print(f"\n== {name}: {len(walls)} seinaa, katvepintoja {len(new)}")
        for w in new:
            L = ((w.axis[1][0] - w.axis[0][0]) ** 2
                 + (w.axis[1][1] - w.axis[0][1]) ** 2) ** 0.5
            print(f"   {w.id:14s} {L/1000:5.1f}m  {w.source.notes:26s} "
                  f"tuki {w.support}  jatkuvuus {w.continuity}")


if __name__ == "__main__":
    main()

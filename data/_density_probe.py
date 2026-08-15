"""Kuinka harva skanni riittää kaatamaan laatumittarit?

Tuki, jatkuvuus ja karsinta nojaavat ABSOLUUTTISIIN pistemääriin
(`_CONT_MIN_PTS` = 5 pistettä / 500 mm sarake, `_SUP_MIN_PTS` = 100). Ne on
viritetty tiheillä keilauksilla. Harvalla skannilla aito seinä voi pudota
kynnyksen alle ja karsiutua PALKKILINJANA — eli väärä poisto, ei vain
puuttuva lippu.

Tämä harventaa saman pilven kertoimilla ja mittaa jokaisella tiheydellä
seinien tuen ja jatkuvuuden sekä sen mitä `prune_unsupported_walls` tekisi.
Ei aja putkea uudelleen: sama malli, eri tiheys → ero on puhtaasti mittarin.

Ajo: .venv/Scripts/python.exe data/_density_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scan2bim.core.qa.deviation import measure_wall_support  # noqa: E402
from scan2bim.core.semantics.wall_semantics import prune_unsupported_walls  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402

MODEL = Path("data/output/_rohbau_site_07_scene_07000/floor_00/model.json")
COORD = Path("data/_rohbau/site_07/scene_07000/coord.npy")
FACTORS = (1, 10, 100, 250, 500, 1000, 2500, 5000)
# Rohbau-GT: nama kaksi OVAT haamuja, joten niiden poisto on oikein.
PHANTOMS = {"wall_ext_001", "wall_ext_007"}


def cloud_of(P):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(P)
    return pc


def main() -> None:
    P = np.load(COORD).astype(np.float64)
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    raw = json.loads(MODEL.read_text(encoding="utf-8"))
    rng = np.random.default_rng(0)
    order = rng.permutation(len(P))

    print(f"täysi pilvi {len(P):,} pistettä, malli {len(raw['walls'])} seinää\n")
    print(f"{'harvennus':>10s} {'pisteitä':>12s} {'tuki med':>9s} {'jatk med':>9s} "
          f"{'jatk min':>9s} {'KARSITTU':>9s}")
    for f in FACTORS:
        sub = P[order[: len(P) // f]]
        model = StructuralModel.model_validate(raw)
        measure_wall_support(model, cloud_of(sub))
        sup = [w.support for w in model.walls if w.support is not None]
        con = [w.continuity for w in model.walls if w.continuity is not None]
        dropped = prune_unsupported_walls(model, cloud_of(sub))
        bad = [d for d in dropped if d not in PHANTOMS]
        flag = "  <== VÄÄRIÄ POISTOJA" if bad else ""
        print(f"1/{f:<8d} {len(sub):12,d} "
              f"{np.median(sup) if sup else float('nan'):9.2f} "
              f"{np.median(con) if con else float('nan'):9.2f} "
              f"{min(con) if con else float('nan'):9.2f} "
              f"{len(bad):9d}{flag}")
        if dropped:
            print(f"           poistettu: {', '.join(dropped)}"
                  f"   (haamuja {len(dropped) - len(bad)})")


if __name__ == "__main__":
    main()

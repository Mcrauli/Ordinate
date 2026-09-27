"""Kannattaako detektoreista tehdä YHDISTELMÄ?

contour ja histogrammi tekevät eri virheitä: contour jättää löytämättä (matala
kattavuus, korkea tarkkuus), histogrammi keksii palkkilinjoja (korkea kattavuus,
matala tarkkuus). Jos evidenssisuodatin osaa hylätä keksityt, unioni voisi
antaa molempien parhaat puolet.

Tämä ajaa kolme varianttia samalla pilvellä ja mittaa ne GT:tä vasten:
  A) vain contour        B) vain histogrammi        C) unioni + evidenssisuodatin

Ajo: .venv/Scripts/python.exe data/_ensemble_probe.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ordinate.core.qa.deviation import measure_wall_support  # noqa: E402
from ordinate.core.semantics.wall_semantics import (  # noqa: E402
    _deduplicate, prune_unsupported_walls,
)
from ordinate.schemas.model import StructuralModel  # noqa: E402

SCENE = Path("data/_rohbau/site_07/scene_07000")
HIST = Path("data/output/_rohbau_site_07_scene_07000/floor_00/model.json")
CONT = Path("data/output/_rohbau_contour_ctrl/floor_00/model.json")
OUT = Path("data/output/_ensemble/floor_00")


def _cloud():
    P = np.load(SCENE / "coord.npy").astype(np.float64)
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    c = o3d.geometry.PointCloud()
    c.points = o3d.utility.Vector3dVector(P)
    return c


def _qa(mj: Path) -> None:
    r = subprocess.run(
        [sys.executable, "data/_rohbau_qa.py", str(mj),
         str(SCENE / "coord.npy"), str(SCENE / "class.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    for line in r.stdout.splitlines():
        if line.startswith(("KATTAVUUS", "TARKKUUS", "ONGELMASEINIA")):
            print("   ", line)


def main() -> None:
    cloud = _cloud()
    hist = StructuralModel.load(HIST)
    cont = StructuralModel.load(CONT)
    print(f"histogrammi {len(hist.walls)} seinaa, contour {len(cont.walls)} seinaa")

    print("\nA) vain contour")
    _qa(CONT)
    print("\nB) vain histogrammi")
    _qa(HIST)

    # C) unioni: molempien seinat, id:t erotellen, dedup, evidenssisuodatin
    merged = StructuralModel.load(HIST)
    for w in hist.walls:
        w.id = f"h_{w.id}"
    extra = []
    for w in cont.walls:
        w.id = f"c_{w.id}"
        extra.append(w)
    merged.walls = _deduplicate(hist.walls + extra)
    merged.openings = []
    print(f"\nC) unioni {len(hist.walls)}+{len(extra)} -> dedup {len(merged.walls)} seinaa")
    measure_wall_support(merged, cloud)
    dropped = prune_unsupported_walls(merged)
    print(f"   evidenssisuodatin poisti {len(dropped)} -> {len(merged.walls)} seinaa")
    OUT.mkdir(parents=True, exist_ok=True)
    merged.slabs = hist.slabs
    merged.save(OUT / "model.json")
    _qa(OUT / "model.json")


if __name__ == "__main__":
    main()

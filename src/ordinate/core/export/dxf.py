"""StructuralModel → DXF."""
from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from ordinate.schemas.model import StructuralModel


def write_dxf(model: StructuralModel, path: Path) -> None:
    doc = ezdxf.new("R2010")
    _setup_layers(doc)
    msp = doc.modelspace()

    for wall in model.walls:
        if len(wall.axis) >= 2:
            p0 = [wall.axis[0][0], wall.axis[0][1], 0.0]
            p1 = [wall.axis[1][0], wall.axis[1][1], 0.0]
            msp.add_line(p0, p1, dxfattribs={"layer": "S-WALLS"})

    for slab in model.slabs:
        layer = "S-FLOORS" if slab.slab_type == "floor" else "S-ROOFS"
        pts = slab.boundary
        if len(pts) >= 3:
            pts_3d = [[p[0], p[1], slab.elevation] for p in pts]
            msp.add_lwpolyline(
                [(p[0], p[1]) for p in pts],
                close=True,
                dxfattribs={"layer": layer, "elevation": slab.elevation},
            )

    doc.saveas(str(path))


def _setup_layers(doc) -> None:
    layers = doc.layers
    for name, color in [
        ("S-WALLS", 1),    # punainen
        ("S-FLOORS", 3),   # vihreä
        ("S-ROOFS", 5),    # sininen
    ]:
        if name not in layers:
            layers.add(name=name, color=color)

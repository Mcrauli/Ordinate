"""StructuralModel → DXF. Stub — laajennetaan M6:ssa."""
from __future__ import annotations

from pathlib import Path

from scan2bim.schemas.model import StructuralModel


def write_dxf(model: StructuralModel, path: Path) -> None:
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for wall in model.walls:
        if len(wall.axis) >= 2:
            msp.add_line(wall.axis[0], wall.axis[1], dxfattribs={"layer": "WALLS"})
    doc.saveas(str(path))

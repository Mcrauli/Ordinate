"""StructuralModel → AutoLISP-skripti. Stub — laajennetaan M6:ssa."""
from __future__ import annotations

from pathlib import Path

from scan2bim.schemas.model import StructuralModel


def write_lsp(model: StructuralModel, path: Path) -> None:
    lines = ["; scan2bim — AutoLISP wall script", "(command \"LAYER\" \"M\" \"WALLS\" \"\")"]
    for wall in model.walls:
        if len(wall.axis) >= 2:
            x0, y0 = wall.axis[0]
            x1, y1 = wall.axis[1]
            lines.append(f'(command "LINE" "{x0},{y0},0" "{x1},{y1},0" "")')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

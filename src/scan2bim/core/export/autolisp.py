"""StructuralModel → AutoLISP-skripti (seinät + laattarajat AutoCADiin)."""
from __future__ import annotations

from pathlib import Path

from scan2bim.schemas.model import StructuralModel


def write_lsp(model: StructuralModel, path: Path) -> None:
    out: list[str] = [
        "; scan2bim — AutoLISP export",
        "; Seinät layer S-WALLS, lattiat S-FLOORS, katot S-ROOFS",
        '(defun _mk-layer (n c / ) (command "LAYER" "M" n "C" (itoa c) n ""))',
        '(_mk-layer "S-WALLS" 1)',
        '(_mk-layer "S-FLOORS" 3)',
        '(_mk-layer "S-ROOFS" 5)',
    ]

    # Seinät — LINE-komennot
    if model.walls:
        out.append('; --- Seinät ---')
        out.append('(command "LAYER" "S" "S-WALLS" "")')
        for wall in model.walls:
            if len(wall.axis) >= 2:
                x0, y0 = wall.axis[0]
                x1, y1 = wall.axis[1]
                out.append(f'(command "LINE" "{x0:.1f},{y0:.1f},0" "{x1:.1f},{y1:.1f},0" "")')

    # Lattiat ja katot — PLINE-komennot
    for slab in model.slabs:
        if len(slab.boundary) < 3:
            continue
        layer = "S-FLOORS" if slab.slab_type == "floor" else "S-ROOFS"
        z = slab.elevation
        out.append(f'; --- {slab.slab_type} z={z:.0f}mm ---')
        out.append(f'(command "LAYER" "S" "{layer}" "")')
        pline_args = " ".join(
            f'"{p[0]:.1f},{p[1]:.1f},{z:.1f}"' for p in slab.boundary[:-1]
        )
        out.append(f'(command "PLINE" {pline_args} "C")')

    path.write_text("\n".join(out) + "\n", encoding="utf-8")

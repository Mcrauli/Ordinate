"""StructuralModel → IFC4-tiedosto. Stub — laajennetaan M6:ssa."""
from __future__ import annotations

from pathlib import Path

from scan2bim.schemas.model import StructuralModel


def write_ifc(model: StructuralModel, path: Path) -> None:
    # TODO M6: ifcopenshell-toteutus (skeleton + builders kuten dwg2ifc)
    path.write_text(f"# scan2bim IFC stub\n# {model.summary()}\n", encoding="utf-8")

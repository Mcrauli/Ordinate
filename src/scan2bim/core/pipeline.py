"""
Pipeline-orkestroija. Ajaa kaikki vaiheet järjestyksessä ja palauttaa StructuralModel.
Kutsu: model = Pipeline(config).run(input_path, output_dir)
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from scan2bim.schemas.model import StructuralModel, Metadata

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    voxel_size: float = 20.0                                   # mm
    detector: Literal["ransac", "density"] = "ransac"
    export_ifc: bool = True
    export_dxf: bool = True
    export_lsp: bool = True


class Pipeline:
    """Koko pistepilvi → malli -putki."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._progress = progress or (lambda msg: log.info(msg))

    def run(self, input_path: Path, output_dir: Path) -> StructuralModel:
        output_dir.mkdir(parents=True, exist_ok=True)

        self._progress(f"Ladataan: {input_path.name}")
        cloud = self._load(input_path)

        self._progress("Esikäsittely (downsample + kohinasuodatus)…")
        cloud = self._preprocess(cloud)

        self._progress(f"Seinädetektio ({self.config.detector})…")
        model = self._detect(cloud, input_path)

        self._progress("Tallennetaan JSON…")
        model.save(output_dir / "model.json")

        if self.config.export_ifc:
            self._progress("Kirjoitetaan IFC…")
            self._write_ifc(model, output_dir / "model.ifc")

        if self.config.export_dxf:
            self._progress("Kirjoitetaan DXF…")
            self._write_dxf(model, output_dir / "model.dxf")

        if self.config.export_lsp:
            self._progress("Kirjoitetaan AutoLISP…")
            self._write_lsp(model, output_dir / "walls.lsp")

        self._progress(f"Valmis. {model.summary()}")
        return model

    # --- yksityiset vaiheet (stub — korvataan M2+ toteutuksilla) -----------

    def _load(self, path: Path):
        from scan2bim.core.geometry.loader import load_point_cloud
        return load_point_cloud(path)

    def _preprocess(self, cloud):
        from scan2bim.core.geometry.preprocess import preprocess
        return preprocess(cloud, voxel_size=self.config.voxel_size)

    def _detect(self, cloud, source_path: Path) -> StructuralModel:
        from scan2bim.core.segmentation.wall_detector import WallDetector
        from scan2bim.core.segmentation.slab_detector import SlabDetector
        walls = WallDetector().detect(cloud)
        slabs = SlabDetector().detect(cloud)
        return StructuralModel(
            walls=walls,
            slabs=slabs,
            metadata=Metadata(
                source_file=source_path.name,
                voxel_size=self.config.voxel_size,
                detector_method=self.config.detector,
            ),
        )

    def _write_ifc(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.ifc.writer import write_ifc
        write_ifc(model, path)

    def _write_dxf(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.export.dxf import write_dxf
        write_dxf(model, path)

    def _write_lsp(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.export.autolisp import write_lsp
        write_lsp(model, path)

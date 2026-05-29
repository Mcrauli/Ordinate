"""
Pipeline-orkestroija. Ajaa kaikki vaiheet järjestyksessä ja palauttaa StructuralModel.
Kutsu: model = Pipeline(config).run(input_path, output_dir)

Välidata tallennetaan output_dir/intermediate/ debuggausta varten.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from scan2bim.schemas.model import StructuralModel, Metadata

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    voxel_size: float = 20.0                           # mm
    detector: Literal["ransac", "density"] = "ransac"
    export_ifc: bool = True
    export_dxf: bool = True
    export_lsp: bool = True
    save_intermediate: bool = True


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
        t0 = time.monotonic()
        output_dir.mkdir(parents=True, exist_ok=True)
        inter = output_dir / "intermediate"
        if self.config.save_intermediate:
            inter.mkdir(exist_ok=True)

        # 1. Lataus
        self._progress(f"Ladataan: {input_path.name}")
        cloud = self._load(input_path)
        n_raw = len(cloud.points)
        self._progress(f"  → {n_raw:,} pistettä ladattu")

        if self.config.save_intermediate:
            self._save_cloud(cloud, inter / "01_loaded.ply")

        # 2. Esikäsittely
        self._progress(f"Esikäsittely (voxel {self.config.voxel_size:.0f} mm)…")
        cloud = self._preprocess(cloud)
        n_pre = len(cloud.points)
        self._progress(f"  → {n_pre:,} pistettä esikäsittelyn jälkeen ({n_pre/n_raw*100:.1f} %)")

        if self.config.save_intermediate:
            self._save_cloud(cloud, inter / "02_preprocessed.ply")

        # 3. Segmentointi + semantiikka
        self._progress("Elementtien tunnistus…")
        model = self._detect(cloud, input_path)
        self._progress(f"  → {model.summary()}")

        if self.config.save_intermediate:
            model.save(inter / "03_model_raw.json")

        # 4. JSON-tallennus
        self._progress("Tallennetaan JSON…")
        model.save(output_dir / "model.json")

        # 5. Export
        if self.config.export_ifc:
            self._progress("Kirjoitetaan IFC…")
            self._write_ifc(model, output_dir / "model.ifc")

        if self.config.export_dxf:
            self._progress("Kirjoitetaan DXF…")
            self._write_dxf(model, output_dir / "model.dxf")

        if self.config.export_lsp:
            self._progress("Kirjoitetaan AutoLISP…")
            self._write_lsp(model, output_dir / "walls.lsp")

        elapsed = time.monotonic() - t0
        self._progress(f"Valmis {elapsed:.1f} s — tulokset: {output_dir.resolve()}")
        return model

    # ------------------------------------------------------------------ #

    def _load(self, path: Path):
        from scan2bim.core.geometry.loader import load_point_cloud
        return load_point_cloud(path)

    def _preprocess(self, cloud):
        from scan2bim.core.geometry.preprocess import preprocess
        return preprocess(cloud, voxel_size=self.config.voxel_size)

    def _detect(self, cloud, source_path: Path) -> StructuralModel:
        from scan2bim.core.segmentation.wall_detector import WallDetector
        from scan2bim.core.segmentation.slab_detector import SlabDetector
        from scan2bim.core.semantics.spaces import derive_spaces

        self._progress("  Seinädetektio (RANSAC)…")
        walls = WallDetector().detect(cloud)
        self._progress(f"    → {len(walls)} seinää")

        self._progress("  Laattadetektio (z-histogram)…")
        slabs = SlabDetector().detect(cloud)
        self._progress(f"    → {len(slabs)} laattaa")

        self._progress("  Pilaridetektio (DBSCAN)…")
        from scan2bim.core.segmentation.column_detector import ColumnDetector
        from scan2bim.core.segmentation.beam_detector import BeamDetector
        from scan2bim.core.semantics.clutter import detect_clutter
        columns = ColumnDetector().detect(cloud)
        self._progress(f"    → {len(columns)} pilaria")

        self._progress("  Palkkidetektio (katto-vyöhyke)…")
        beams = BeamDetector().detect(cloud)
        self._progress(f"    → {len(beams)} palkkia")

        self._progress("  Tilojen johtaminen…")
        partial = StructuralModel(walls=walls, slabs=slabs, columns=columns, beams=beams)
        spaces = derive_spaces(partial)
        self._progress(f"    → {len(spaces)} tilaa")

        self._progress("  Krääsäanalyysi…")
        discarded = detect_clutter(cloud, partial)
        self._progress(f"    → {discarded.clutter_cluster_count} klusteria merkitty krääsäksi")

        return StructuralModel(
            walls=walls,
            slabs=slabs,
            columns=columns,
            beams=beams,
            spaces=spaces,
            discarded=discarded,
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

    @staticmethod
    def _save_cloud(cloud, path: Path) -> None:
        try:
            import open3d as o3d
            o3d.io.write_point_cloud(str(path), cloud)
        except Exception as e:
            log.warning("Välidatan tallennus epäonnistui: %s", e)

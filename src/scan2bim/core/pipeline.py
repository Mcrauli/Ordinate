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
    save_intermediate: bool = True


class Pipeline:
    """Koko pistepilvi -> malli -putki."""

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
        self._progress(f"  -> {n_raw:,} pistettä ladattu")

        if self.config.save_intermediate:
            self._save_cloud(cloud, inter / "01_loaded.ply")

        # 2. Esikäsittely
        self._progress(f"Esikäsittely (voxel {self.config.voxel_size:.0f} mm)…")
        cloud = self._preprocess(cloud)
        n_pre = len(cloud.points)
        self._progress(f"  -> {n_pre:,} pistettä esikäsittelyn jälkeen ({n_pre/n_raw*100:.1f} %)")

        if self.config.save_intermediate:
            self._save_cloud(cloud, inter / "02_preprocessed.ply")

        # 3. Segmentointi + semantiikka
        self._progress("Elementtien tunnistus…")
        model = self._detect(cloud, input_path)
        self._progress(f"  -> {model.summary()}")

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

        elapsed = time.monotonic() - t0
        self._progress(f"Valmis {elapsed:.1f} s — tulokset: {output_dir.resolve()}")
        return model

    def run_floors(self, paths: list[Path], output_dir: Path) -> list[StructuralModel]:
        """Monikerros/multiscan: havaitsee kerrokset Z-histogrammista ja käsittelee
        yhden kerroksen kerrallaan (muistitehokas). Per kerros: floor_NN/model.{json,ifc,dxf}."""
        output_dir.mkdir(parents=True, exist_ok=True)
        self._progress(f"Skannaustiedostoja: {len(paths)}")
        self._progress("Havaitaan kerroksia Z-histogrammista…")

        from scan2bim.core.geometry.floor_splitter import detect_floors_from_files
        from scan2bim.core.geometry.streaming import load_floor_slice

        sample = max(1, len(paths) // 20)
        floors = detect_floors_from_files(paths, sample_step=sample)
        self._progress(f"Löydettiin {len(floors)} kerros(ta).")

        source = paths[0]
        models: list[StructuralModel] = []
        for i, (z_lo, z_hi) in enumerate(floors):
            self._progress(f"Kerros {i + 1}/{len(floors)}  (Z {z_lo/1000:.2f}–{z_hi/1000:.2f} m)…")
            cloud = load_floor_slice(
                paths, z_lo, z_hi,
                voxel_size=self.config.voxel_size,
                progress_cb=self._progress,
            )
            if len(cloud.points) < 500:
                self._progress(f"  Liian vähän pisteitä ({len(cloud.points)}), ohitetaan.")
                continue

            self._progress(f"  Pisteitä: {len(cloud.points):,} — kohinasuodatus…")
            cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)

            model = self._detect(cloud, source)
            model.metadata.floor_index = i
            model.metadata.floor_count = len(floors)

            floor_dir = output_dir / f"floor_{i:02d}"
            floor_dir.mkdir(exist_ok=True)
            model.save(floor_dir / "model.json")
            if self.config.export_ifc:
                self._write_ifc(model, floor_dir / "model.ifc")
            if self.config.export_dxf:
                self._write_dxf(model, floor_dir / "model.dxf")
            self._progress(f"  {model.summary()}")
            models.append(model)

        self._progress(f"Valmis. {len(models)} kerrosta käsitelty.")
        return models

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

        from scan2bim.core.segmentation.column_detector import ColumnDetector
        from scan2bim.core.segmentation.beam_detector import BeamDetector
        from scan2bim.core.semantics.clutter import detect_clutter
        from scan2bim.core.semantics.wall_pairing import refine_wall_thicknesses

        # Ketjutettu inlier-subtraktio: jokainen detektori poistaa omat pisteensä
        self._progress("  Seinädetektio (RANSAC)…")
        walls_raw, cloud1 = WallDetector().detect(cloud)
        self._progress(f"    -> {len(walls_raw)} seinää  ({len(cloud1.points):,} pt jäljellä)")

        self._progress("  Seinäpaksuuden tarkennus…")
        walls = refine_wall_thicknesses(walls_raw)
        thick_ok = sum(1 for w in walls if w.thickness >= 50)
        self._progress(f"    -> {thick_ok}/{len(walls)} seinällä mitattu/arvioitu paksuus")

        self._progress("  Laattadetektio (z-histogram)…")
        slabs, cloud2 = SlabDetector().detect(cloud1)
        self._progress(f"    -> {len(slabs)} laattaa  ({len(cloud2.points):,} pt jäljellä)")

        self._progress("  Pilaridetektio (DBSCAN)…")
        columns, cloud3 = ColumnDetector().detect(cloud2)
        self._progress(f"    -> {len(columns)} pilaria  ({len(cloud3.points):,} pt jäljellä)")

        self._progress("  Palkkidetektio (katto-vyöhyke)…")
        beams, cloud4 = BeamDetector().detect(cloud3)
        self._progress(f"    -> {len(beams)} palkkia  ({len(cloud4.points):,} pt jäljellä)")

        self._progress("  Tilojen johtaminen…")
        partial = StructuralModel(walls=walls, slabs=slabs, columns=columns, beams=beams)
        spaces = derive_spaces(partial)
        self._progress(f"    -> {len(spaces)} tilaa")

        self._progress("  Krääsäanalyysi (jäljellä olevista pisteistä)…")
        discarded = detect_clutter(cloud4, partial)
        self._progress(f"    -> {discarded.clutter_cluster_count} klusteria merkitty krääsäksi")

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

    @staticmethod
    def _save_cloud(cloud, path: Path) -> None:
        try:
            import open3d as o3d
            o3d.io.write_point_cloud(str(path), cloud)
        except Exception as e:
            log.warning("Välidatan tallennus epäonnistui: %s", e)

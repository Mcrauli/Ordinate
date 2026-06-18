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

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from scan2bim.schemas.model import StructuralModel, Metadata

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    voxel_size: float = 12.0                                   # mm (manuaalinen, kun auto_voxel=False)
    auto_voxel: bool = True            # valitse voxelikoko datasta automaattisesti
    detector: Literal["ransac", "density", "floorplan", "normals"] = "normals"
    export_ifc: bool = True
    export_dxf: bool = True
    export_qa: bool = True                                     # QA/LOA-poikkeamaraportti
    qa_tolerance: float = 2.5                                  # mm
    icp_refine: bool = False                                   # ICP-hienorekisteröinti monoskannauksille
    save_intermediate: bool = False


_AUTO_TARGET_POINTS = 4_000_000
_AUTO_VOXEL_MIN = 8.0
_AUTO_VOXEL_MAX = 25.0


def _auto_voxel(cloud, target: int = _AUTO_TARGET_POINTS) -> float:
    """Valitse voxelikoko niin että työpilvi on ~target pistettä (yksi halpa arvio)."""
    ref = 20.0
    n_ref = len(cloud.voxel_down_sample(ref).points)
    if n_ref <= target:
        return _AUTO_VOXEL_MIN
    v = ref * float(np.sqrt(n_ref / target))
    return round(min(max(v, _AUTO_VOXEL_MIN), _AUTO_VOXEL_MAX), 1)


def _recenter_wall_axes(walls, cloud) -> list:
    """Korjaa seinäakselin ja paksuuden leveällä histogrammilla — ei luota alkupaksuuteen."""
    pts = np.asarray(cloud.points)
    return [_fix_wall_center(w, pts) for w in walls]


def _trim_wall_endpoints(walls, cloud) -> list:
    """Trimmaa seinien päätepisteet vastaamaan todellista pistepilvidataa."""
    pts = np.asarray(cloud.points)
    return [_trim_endpoints(w, pts) for w in walls]


def _trim_endpoints(wall, pts: np.ndarray):
    if len(wall.axis) < 2:
        return wall
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 1.0:
        return wall

    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    axis_D = float(np.dot(normal, p0))

    half_t = wall.thickness / 2.0
    face_tol = 30.0
    z_lo = wall.z_min - 50.0
    z_hi = wall.z_min + wall.height + 50.0

    dist = np.abs(pts[:, :2] @ normal - axis_D)
    along_proj = (pts[:, :2] - p0) @ along

    # Ota pisteet seinän pinnoilta (±30mm käy)
    on_face = (
        ((np.abs(dist - half_t) < face_tol) | (dist < face_tol))
        & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    )
    if on_face.sum() < 20:
        return wall

    face_along = along_proj[on_face]
    lo = float(np.percentile(face_along, 2))
    hi = float(np.percentile(face_along, 98))

    _MARGIN = 5.0        # mm — pieni reuna päätepisteiden ympärillä
    _MAX_EXTEND = 300.0  # mm — älä pidennä yli tämän (T-liitos tai dataaukko)

    ax = [list(wall.axis[0]), list(wall.axis[1])]
    changed = False

    # p0: trimmaa jos data alkaa sisempänä, pidennä jos data alkaa ulompana
    if lo > _MARGIN:
        new_p0 = p0 + (lo - _MARGIN) * along
        ax[0] = [round(float(new_p0[0]), 1), round(float(new_p0[1]), 1)]
        changed = True
    elif lo < -_MARGIN and abs(lo) <= _MAX_EXTEND:
        new_p0 = p0 + (lo + _MARGIN) * along
        ax[0] = [round(float(new_p0[0]), 1), round(float(new_p0[1]), 1)]
        changed = True

    # p1: trimmaa jos data loppuu sisempänä, pidennä jos data jatkuu ulompana
    if hi < length - _MARGIN:
        new_p1 = p0 + (hi + _MARGIN) * along
        ax[1] = [round(float(new_p1[0]), 1), round(float(new_p1[1]), 1)]
        changed = True
    elif hi > length + _MARGIN and (hi - length) <= _MAX_EXTEND:
        new_p1 = p0 + (hi - _MARGIN) * along
        ax[1] = [round(float(new_p1[0]), 1), round(float(new_p1[1]), 1)]
        changed = True

    return wall.model_copy(update={"axis": ax}) if changed else wall


def _fix_wall_center(wall, pts: np.ndarray):
    if len(wall.axis) < 2:
        return wall
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 1.0:
        return wall

    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    axis_D = float(np.dot(normal, p0))

    z_lo = wall.z_min + 200.0
    z_hi = wall.z_min + wall.height - 200.0
    along_proj = (pts[:, :2] - p0) @ along
    dist = pts[:, :2] @ normal - axis_D

    mask = (
        (along_proj >= 100.0) & (along_proj <= length - 100.0)
        & (np.abs(dist) <= 650.0)
        & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    )
    if mask.sum() < 40:
        return wall

    d_vals = dist[mask]
    # Bin-alkupiste -653.75 → bin-keskipisteet osuvat 5mm-bin-keskipisteisiin (±62.5, ±157.5 jne.)
    hist, edges = np.histogram(d_vals, bins=np.arange(-653.75, 656.25, 2.5))
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = uniform_filter1d(hist.astype(float), size=3)
    pks, _ = find_peaks(smooth, height=smooth.max() * 0.08, distance=20)

    if len(pks) < 2:
        return wall

    T_ref = wall.thickness
    dist_limit = 600.0
    best_pair: tuple[float, float] | None = None
    best_score = 0.0
    for ii in range(len(pks)):
        for jj in range(ii + 1, len(pks)):
            da = float(centers[pks[ii]])
            db = float(centers[pks[jj]])
            if abs(da) > dist_limit or abs(db) > dist_limit:
                continue
            t_pair = abs(da - db)
            if not (50.0 <= t_pair <= 450.0):
                continue
            t_weight = 1.0 / (1.0 + abs(t_pair - T_ref) / 50.0)
            score = (smooth[pks[ii]] + smooth[pks[jj]]) * t_weight
            if score > best_score:
                best_score = score
                best_pair = (da, db)

    if best_pair is None:
        return wall

    d1, d2 = best_pair
    t_new = abs(d1 - d2)
    center_offset = (d1 + d2) / 2.0

    if not (50.0 <= t_new <= 450.0):
        return wall

    updates: dict = {}
    if abs(center_offset) >= 1.0:
        shift_vec = center_offset * normal
        updates["axis"] = [
            [round(p0[0] + shift_vec[0], 1), round(p0[1] + shift_vec[1], 1)],
            [round(p1[0] + shift_vec[0], 1), round(p1[1] + shift_vec[1], 1)],
        ]
    if abs(t_new - wall.thickness) >= 2.0:
        updates["thickness"] = round(t_new, 1)

    return wall.model_copy(update=updates) if updates else wall


class Pipeline:
    """Koko pistepilvi → malli -putki."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._progress = progress or (lambda msg: log.info(msg))
        self._scanner_origins: list = []   # täytetään kerroskohtaisesti (E57)

    def run(self, input_path: Path | list[Path], output_dir: Path) -> StructuralModel:
        output_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(input_path, list):
            paths = input_path
            if len(paths) == 1:
                self._progress(f"Ladataan: {paths[0].name}")
            else:
                self._progress(f"Ladataan {len(paths)} skannia ja yhdistetään…")
            cloud = self._load_many(paths)
            input_path = paths[0]
        else:
            self._progress(f"Ladataan: {input_path.name}")
            cloud = self._load(input_path)

        if self.config.auto_voxel:
            self.config.voxel_size = _auto_voxel(cloud)
            self._progress(f"  Auto-voxel: {self.config.voxel_size:.1f} mm")

        self._progress("Esikäsittely (downsample + kohinasuodatus)…")
        # 5mm downsample endpoint-tarkkuutta varten — tarkempi kuin detektiovoxel mutta nopea
        _REFINE_VOXEL = 5.0
        refine_cloud = cloud.voxel_down_sample(_REFINE_VOXEL) if len(cloud.points) > 200_000 else cloud
        cloud = self._preprocess(cloud)

        self._progress(f"Seinädetektio ({self.config.detector})…")
        model = self._detect(cloud, input_path, refine_cloud=refine_cloud)

        self._progress("Tallennetaan JSON…")
        model.save(output_dir / "model.json")

        if self.config.export_ifc:
            self._progress("Kirjoitetaan IFC…")
            self._write_ifc(model, output_dir / "model.ifc")

        if self.config.export_dxf:
            self._progress("Kirjoitetaan DXF…")
            self._write_dxf(model, output_dir / "model.dxf")

        self._progress("Kirjoitetaan debug-pilvi…")
        self._write_debug(model, output_dir / "debug.ply")

        self._progress(f"Valmis. {model.summary()}")
        return model

    def run_floors(self, paths: list[Path], output_dir: Path) -> list[StructuralModel]:
        """Kerrosjako-putki: lataa yhden kerroksen kerrallaan, ei muistirajoitusta."""
        output_dir.mkdir(parents=True, exist_ok=True)

        self._progress(f"Skannaustiedostoja: {len(paths)}")
        self._progress("Havaitaan kerroksia Z-histogrammista…")

        from scan2bim.core.geometry.floor_splitter import detect_floors_from_files
        import math
        # Kerrosjako tarvitsee vain Z-jakauman → riittää ~4 hajautettua tiedostoa
        # (kattaa kerrokset), ei kaikkien lukua. Säästää I/O:ta isolla setillä.
        sample = max(1, math.ceil(len(paths) / 4))
        floors = detect_floors_from_files(paths, sample_step=sample)
        self._progress(f"Löydettiin {len(floors)} kerros(ta).")

        if self.config.auto_voxel:
            self.config.voxel_size = 12.0
            self._progress(f"  Auto-voxel: {self.config.voxel_size:.1f} mm")

        source = paths[0]
        models: list[StructuralModel] = []

        for floor_idx, (z_lo, z_hi) in enumerate(floors):
            self._progress(
                f"Kerros {floor_idx + 1}/{len(floors)}  "
                f"(Z {z_lo/1000:.2f}–{z_hi/1000:.2f} m)…"
            )

            from scan2bim.core.geometry.streaming import load_floor_slice
            cloud = load_floor_slice(
                paths, z_lo, z_hi,
                voxel_size=self.config.voxel_size,
                progress_cb=self._progress,
                icp_refine=self.config.icp_refine,
            )

            if len(cloud.points) < 500:
                self._progress(f"  Liian vähän pisteitä ({len(cloud.points)}), ohitetaan.")
                continue

            # Kohinasuodatus aina: voxelointi ei poista harhapisteitä, ja ne
            # sotkevat seinien koordinaatit + tuottavat valehavaintoja. Tarkkuus > nopeus.
            self._progress(f"  Pisteitä: {len(cloud.points):,} — kohinasuodatus…")
            cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)

            from scan2bim.core.geometry.loader import scanner_origins
            origins: list = []
            for p in paths:
                for o in scanner_origins(p):
                    if z_lo <= float(o[2]) <= z_hi:
                        origins.append(o)
            self._scanner_origins = origins
            if origins:
                self._progress(f"  Skannerin origoja: {len(origins)} (okkluusiosuodatus päällä)")

            self._progress(f"  Seinädetektio ({self.config.detector})…")
            model = self._detect(cloud, source)
            model.metadata.floor_index = floor_idx
            model.metadata.floor_count = len(floors)

            floor_dir = output_dir / f"floor_{floor_idx:02d}"
            floor_dir.mkdir(exist_ok=True)
            model.save(floor_dir / "model.json")

            if self.config.export_ifc:
                self._write_ifc(model, floor_dir / "model.ifc")
                if self.config.export_qa:
                    try:
                        from scan2bim.core.qa.deviation import write_qa_report
                        res = write_qa_report(
                            model, cloud, floor_dir / "model.ifc",
                            floor_dir / "qa_report.txt", tol=self.config.qa_tolerance,
                        )
                        ov = res["deviation"].get("overall", {})
                        self._progress(
                            f"  QA: {ov.get('within_tol_pct', '?')} % <= {self.config.qa_tolerance} mm, "
                            f"{len(res['flags'])} tarkistettavaa"
                        )
                    except Exception as e:
                        self._progress(f"  QA-raportti ohitettu: {e}")
            if self.config.export_dxf:
                self._write_dxf(model, floor_dir / "model.dxf")
            self._write_debug(model, floor_dir / "debug.ply")

            self._progress(f"  {model.summary()}")
            models.append(model)

        if models:
            if self.config.export_ifc and len(models) >= 1:
                from scan2bim.core.ifc.writer import write_building_ifc
                write_building_ifc(models, output_dir / "building.ifc")
                self._progress(f"Koko talo: {output_dir / 'building.ifc'}")
            self._progress(f"Valmis. {len(models)} kerrosta käsitelty.")
        return models

    # --- yksityiset vaiheet ---------------------------------------------------

    def _load(self, path: Path):
        from scan2bim.core.geometry.loader import load_point_cloud
        return load_point_cloud(path)

    def _load_many(self, paths: list[Path]):
        from scan2bim.core.geometry.loader import load_and_merge
        return load_and_merge(paths)

    def _preprocess(self, cloud):
        from scan2bim.core.geometry.preprocess import preprocess
        return preprocess(cloud, voxel_size=self.config.voxel_size)

    def _detect(self, cloud, source_path: Path, refine_cloud=None) -> StructuralModel:
        import scan2bim.core.segmentation.wall_ransac  # noqa: F401
        import scan2bim.core.segmentation.wall_density  # noqa: F401
        import scan2bim.core.segmentation.wall_normals  # noqa: F401
        import scan2bim.core.floorplan.detector  # noqa: F401
        from scan2bim.core.segmentation.base import DetectorRegistry
        from scan2bim.core.segmentation.slab_detector import detect_slabs

        from scan2bim.core.semantics.wall_semantics import filter_structural_walls, refine_thicknesses
        from scan2bim.core.semantics.corner_snap import snap_corners

        detector = DetectorRegistry.get(self.config.detector)()
        model = detector.detect(cloud)
        model.slabs = detect_slabs(cloud)
        model.walls = filter_structural_walls(model.walls, model.slabs)
        model.walls = refine_thicknesses(model.walls, cloud)
        model.walls = _recenter_wall_axes(model.walls, cloud)

        # Toinen deduplikointi: akselinkorjaus saattaa tuoda aiemmin eri paikassa olevia
        # seiniä samalle akselille (kuten wall_105/wall_108 jotka ovat saman seinän pinnat)
        from scan2bim.core.semantics.wall_semantics import _deduplicate
        model.walls = _deduplicate(model.walls)

        model.walls = snap_corners(model.walls)
        trim_cloud = refine_cloud if refine_cloud is not None else cloud
        model.walls = _trim_wall_endpoints(model.walls, trim_cloud)
        model.walls = snap_corners(model.walls)  # reconnektoi trim:in katkaisevat nurkat

        # Normalisoi seinien korkeus lattia-katto-välille (tarkka arkkitehtimalli)
        floor_z = min(
            (s.elevation for s in model.slabs if s.slab_type == "floor"),
            default=float(min((w.z_min for w in model.walls), default=0.0)),
        )
        ceiling_z = max(
            (s.elevation for s in model.slabs if s.slab_type == "ceiling"),
            default=float(max((w.z_min + w.height for w in model.walls), default=floor_z + 2700.0)),
        )
        room_height = round(ceiling_z - floor_z, 1)
        if room_height > 500.0:
            model.walls = [
                w.model_copy(update={"z_min": round(floor_z, 1), "height": room_height})
                for w in model.walls
            ]

        # Korvaa laatan rajapisteet seinien leikkauspisteistä johdetulla polygonilla
        from scan2bim.core.semantics.room_polygon import build_room_polygon, snap_walls_to_polygon
        room_poly = build_room_polygon(model.walls)
        if room_poly and len(room_poly) >= 3:
            model.slabs = [s.model_copy(update={"boundary": room_poly}) for s in model.slabs]

        from scan2bim.core.segmentation.opening_detector import detect_openings
        model.openings = detect_openings(model.walls, cloud, floor_z, scanner_origins=self._scanner_origins)

        from scan2bim.core.segmentation.column_detector import detect_columns
        model.columns = detect_columns(cloud, model.walls, floor_z, ceiling_z)

        model.metadata.source_file = source_path.name
        model.metadata.voxel_size = self.config.voxel_size
        return model

    def _write_ifc(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.ifc.writer import write_ifc
        write_ifc(model, path)

    def _write_dxf(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.export.dxf import write_dxf
        write_dxf(model, path)

    def _write_debug(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.export.debug_cloud import write_debug_cloud
        floor_z = min(
            (s.elevation for s in model.slabs if s.slab_type == "floor"),
            default=float(min((w.z_min for w in model.walls), default=0.0)),
        )
        write_debug_cloud(model, path, floor_z, z_offset=0.0)

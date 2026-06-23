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
    detector: Literal["ransac", "density", "floorplan", "normals", "contour"] = "contour"
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


def _recenter_wall_axes(walls, cloud, band: float | None = None, keep_thickness: bool = False) -> list:
    """Pintalukittu tarkennus: mallin lähin pinta osuu skannattuun pistepintaan (bias→0)."""
    pts = np.asarray(cloud.points)
    return [_surface_lock_wall(w, pts, band=band, keep_thickness=keep_thickness) for w in walls]


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


# --- pintalukittu tarkennus -------------------------------------------------
# Tavoite: mallin LÄHIN pinta osuu skannattuun pistepintaan, ei thickness/2 ohi.
# Yksipuolisesti keilatuille seinille (sisätilakeilaus) detektoitu akseli istuu
# pinnan päällä; symmetrinen paksuus työntäisi pinnan ~thickness/2 ohi. Lukitaan
# lähin pinta huippuun ja kasvatetaan paksuus huoneesta POISPÄIN.

_SL_BAND = 280.0           # mm — kohtisuora hakukaista (kapea: ei naapuriseinää)
_SL_MIN_PTS = 60           # min pisteitä jotta tarkennetaan
_SL_BIN = 5.0              # mm histogrammin resoluutio
_SL_MIN_THICK = 60.0       # mm
_SL_MAX_THICK = 380.0      # mm
_SL_DEFAULT_THICK = 120.0  # mm — sisäväliseinän oletus kun toista pintaa ei nähdä
_SL_DOM_BAND = 120.0       # mm — dominantti pinta haetaan akselin läheltä (detektori jättää akselin pinnalle)
_SL_PARTNER_FRAC = 0.45    # toisen pinnan oltava väh. tämä osuus dominantin pisteistä → aito pari
_SL_ROOM_LO = 150.0        # mm — huonepuolen pisteenlaskenta alkaa tästä huipusta
_SL_ROOM_HI = 700.0        # mm — ja päättyy tähän


def _fix_wall_center(wall, pts: np.ndarray):
    """Vanha nimi taaksepäinyhteensopivuudelle; delegoi pintalukitukseen."""
    return _surface_lock_wall(wall, pts)


def _surface_lock_wall(wall, pts: np.ndarray, band: float | None = None, keep_thickness: bool = False):
    sl_band = band if band is not None else _SL_BAND
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
        & (np.abs(dist) <= sl_band)
        & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    )
    if mask.sum() < _SL_MIN_PTS:
        return wall

    d_vals = dist[mask]
    edges = np.arange(-sl_band, sl_band + _SL_BIN, _SL_BIN)
    hist, edges = np.histogram(d_vals, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = uniform_filter1d(hist.astype(float), size=3)
    pks, _ = find_peaks(smooth, height=smooth.max() * 0.20, distance=4)
    if len(pks) == 0:
        return wall

    # Dominantti SKANNATTU pinta: vahvin huippu akselin läheltä. Detektoiduilla
    # seinillä akseli on pinnan päällä → rajaa ±_SL_DOM_BAND (ei naapuriseinää).
    if keep_thickness:
        # Perimetriseinä: akseli on jo siirretty ULOS thickness/2, joten odotettu
        # SISÄPINTA on ~+thickness/2 kohdalla. Etsi huippu sen ympäriltä → pieni
        # korjaus oikeaan sisäpintaan, ei naapuriseinän nappaamista väärältä puolelta.
        exp = wall.thickness / 2.0
        win = 100.0
        cand = [p for p in pks if abs(float(centers[p]) - exp) <= win]
        if not cand:
            return wall
        dom = int(max(cand, key=lambda p: smooth[p]))
    else:
        near = [p for p in pks if abs(float(centers[p])) <= _SL_DOM_BAND]
        cand = near if near else list(pks)
        dom = int(max(cand, key=lambda p: smooth[p]))
    surf = float(centers[dom])
    dom_h = float(smooth[dom])

    # Toinen pinta: lähin riittävän vahva huippu joka antaa järkevän paksuuden.
    # Vaaditaan että sillä on oikeasti pisteitä (PARTNER_FRAC dominantista),
    # muuten kyseessä on yksipuolinen seinä eikä kohinapiikki/naapuri.
    # keep_thickness (perimetriseinä): pakota yksipuolinen haara → lukitse vain
    # sisäpinta, säilytä annettu paksuus (ei naapuriseinän nappaamista).
    best_partner: int | None = None
    best_t = 1e9
    if not keep_thickness:
        for q in pks:
            if int(q) == dom:
                continue
            t_pair = abs(float(centers[q]) - surf)
            if not (_SL_MIN_THICK <= t_pair <= _SL_MAX_THICK):
                continue
            if float(smooth[q]) < _SL_PARTNER_FRAC * dom_h:
                continue
            if t_pair < best_t:
                best_t = t_pair
                best_partner = int(q)

    if best_partner is not None:
        # KAKSI pintaa nähty → akseli pintojen puoliväliin, paksuus = pintaero.
        other = float(centers[best_partner])
        t_new = abs(surf - other)
        center_offset = 0.5 * (surf + other)
    elif keep_thickness:
        # Perimetriseinä: surf = todellinen SISÄPINTA (etsitty +thickness/2:n läheltä).
        # Lukitse sisäpinta siihen, säilytä paksuus → akseli = surf - thickness/2.
        t_new = wall.thickness
        room_sign = 1.0 if surf >= 0.0 else -1.0
        center_offset = surf - room_sign * (t_new / 2.0)
    else:
        # YKSI pinta → lukitse lähin (huoneenpuoleinen) pinta huippuun. Huoneen
        # puoli = enemmän pisteitä huipun takana (avoin tila); seinärunko menee
        # siitä poispäin → mallin lähin pinta osuu skannattuun pintaan (bias→0).
        left = float(((d_vals > surf - _SL_ROOM_HI) & (d_vals < surf - _SL_ROOM_LO)).sum())
        right = float(((d_vals > surf + _SL_ROOM_LO) & (d_vals < surf + _SL_ROOM_HI)).sum())
        room_sign = 1.0 if right >= left else -1.0
        t_new = wall.thickness
        if not (_SL_MIN_THICK <= t_new <= _SL_MAX_THICK):
            t_new = _SL_DEFAULT_THICK
        center_offset = surf - room_sign * (t_new / 2.0)

    if not (_SL_MIN_THICK <= t_new <= _SL_MAX_THICK):
        return wall

    updates: dict = {}
    if abs(center_offset) >= 0.5:
        shift_vec = center_offset * normal
        updates["axis"] = [
            [round(p0[0] + shift_vec[0], 1), round(p0[1] + shift_vec[1], 1)],
            [round(p1[0] + shift_vec[0], 1), round(p1[1] + shift_vec[1], 1)],
        ]
    if abs(t_new - wall.thickness) >= 1.0:
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
        import scan2bim.core.segmentation.wall_contour  # noqa: F401
        import scan2bim.core.floorplan.detector  # noqa: F401
        from scan2bim.core.segmentation.base import DetectorRegistry
        from scan2bim.core.segmentation.slab_detector import detect_slabs

        from scan2bim.core.semantics.wall_semantics import filter_structural_walls, refine_thicknesses
        from scan2bim.core.semantics.corner_snap import snap_corners

        detector = DetectorRegistry.get(self.config.detector)()
        model = detector.detect(cloud)
        model.slabs = detect_slabs(cloud)

        # Lattian todellinen ulkokontuuri (ennen kuin room_polygon korvaa sen
        # konveksilla kuorella) → perimetriseinien lähde.
        floor_contour = next(
            (s.boundary for s in model.slabs if s.slab_type == "floor"), None
        )

        # Pintalukitus tarvitsee mahd. tarkan pilven: 12mm-detektiovoxelin
        # sentroidi-bias siirtää yksipuolisen pinnan ~sisäänpäin. Hienompi
        # refine_cloud (5mm) → bias laskee mediaani ~13mm→~3mm.
        lock_cloud = refine_cloud if refine_cloud is not None else cloud

        model.walls = filter_structural_walls(model.walls, model.slabs)
        model.walls = refine_thicknesses(model.walls, lock_cloud)
        model.walls = _recenter_wall_axes(model.walls, lock_cloud)

        # Toinen deduplikointi: akselinkorjaus saattaa tuoda aiemmin eri paikassa olevia
        # seiniä samalle akselille (kuten wall_105/wall_108 jotka ovat saman seinän pinnat)
        # Täydennä perimetri lattian ulkorajasta — sulkee ulkoseinät joita
        # detektori ei nappaa (keilausvarjot/ikkunat/kalusteet).
        if floor_contour:
            floor_z_w = min((w.z_min for w in model.walls), default=0.0)
            wall_h = max((w.height for w in model.walls), default=2700.0)
            from scan2bim.core.semantics.perimeter import add_perimeter_walls
            # add_perimeter_walls siirtää akselin ulospäin thickness/2 → sisäpinta
            # osuu lattiakontuuriin. Tarkennetaan vielä todelliseen sisäpintaan:
            # keep_thickness säilyttää 300mm-paksuuden eikä nappaa naapuriseinää.
            perim = add_perimeter_walls(
                floor_contour, model.walls, floor_z_w, wall_h
            )
            perim = _recenter_wall_axes(perim, lock_cloud, band=300.0, keep_thickness=True)
            model.walls = model.walls + perim

        from scan2bim.core.semantics.wall_semantics import _deduplicate
        model.walls = _deduplicate(model.walls)

        # Suorista seinät kahteen kohtisuoraan suuntaan ennen kulmien yhdistämistä —
        # vinot seinät eivät muuten kohtaa puhtaasti eivätkä huoneet sulkeudu.
        from scan2bim.core.semantics.orthogonal import regularize_orthogonal
        model.walls = regularize_orthogonal(model.walls)

        model.walls = snap_corners(model.walls)
        trim_cloud = refine_cloud if refine_cloud is not None else cloud
        model.walls = _trim_wall_endpoints(model.walls, trim_cloud)
        model.walls = snap_corners(model.walls)  # reconnektoi trim:in katkaisevat nurkat

        # Poista irralliset tynkäseinät (pää ilmassa, ei rajaa huonetta)
        from scan2bim.core.semantics.wall_semantics import remove_dangling_walls
        model.walls = remove_dangling_walls(model.walls)

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

        from scan2bim.core.semantics.room_detector import detect_rooms
        model.spaces = detect_rooms(model.walls, floor_z, ceiling_z)

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

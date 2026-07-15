"""Palkkidetektori: DBSCAN katto-vyöhykkeessä + pitkänomaiset klusterit.

Algoritmi:
  1. Rajataan pisteet lähelle kattoa (z > z_max - sub_ceiling_mm).
  2. DBSCAN XY-tasoon projisoituna (kuten ColumnDetector).
  3. Pitkänomaiset klusterit (aspekti ≥ min_aspect) → palkit.
  4. Akseli: PCA XY-tasossa → 3D-päätepisteet z-keskiarvolla.
"""
from __future__ import annotations

import uuid
import logging

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import Beam, BeamProfile, ElementSource
from .base import ElementDetector

log = logging.getLogger(__name__)

_MIN_INLIERS = 30
_MIN_ASPECT = 3.0          # length/width — alle tämän = pilari, ei palkki
_MIN_LENGTH_MM = 700.0     # alle tämän = kattokrääsän/putken pätkä, ei palkki
                           # (aidot Rohbau-palkit useimmat >1200mm)
_MAX_WIDTH_MM = 600.0      # palkin max-leveys (ei katto/laatta)
_MIN_HEIGHT_MM = 50.0      # palkin min-z-ulottuvuus (depth)

# Soffit-kiinnitys: aito alaslaskettu palkki valetaan kattolaatan kanssa yhteen →
# sen kyljet ulottuvat YLÖS kattoon asti (max-z lähellä kattoa). Ripustettu
# talotekniikka (putket/kanavat/kaapelihyllyt) roikkuu katosta IRTI — väli jää.
# Vaadi valmiissa tilassa (kattolaatta löytyi) että klusterin lakipiste yltää
# tähän etäisyyteen katosta; muuten = roikkuva LVIS, ei palkki. Tämä on juuri se
# ero joka tuottaa valepalkkeja MEP-täyteisissä liike/toimistotiloissa.
_SOFFIT_ATTACH_MM = 130.0

# Valmiissa tilassa aito palkki ei ole hiuksenohut — kattoon kiinnittyneet ohuet
# pitkänomaiset klusterit ovat putkia/kaapelihyllyjä/johtokouruja, eivät palkkeja.
_FINISHED_MIN_WIDTH_MM = 150.0

_BEAM_WALL_MARGIN = 150.0   # mm — tätä lähempänä seinälinjaa olevat pisteet pois
_SOFFIT_BAND = 800.0        # mm — palkkikaista katon alapinnasta (syvemmällä = TATE-roikku)
                            # (seinän yläosa on pitkänomainen klusteri = valepalkki)

# HEADROOM: aidon palkin ALTA kävelee — sen alapuolella keskikorkeudella on tyhjää.
# Kalustepatterin/hyllyn päällä oleva valepalkki istuu täydellä massalla (mitattu
# 3DSES-huoneesta: palkin alla ~100k pistettä koko matkalta). Valmiissa tilassa
# (kattolaatta tiedossa) jaetaan palkin jänne soluihin: jos liian moni solu on
# "tukossa" (pisteitä suoraan alla keskikorkeudella), klusteri ei ole vapaa palkki.
_HEADROOM_LO = 1000.0        # mm lattiasta — alaraja tarkistuskaistalle
_HEADROOM_GAP = 200.0        # mm — palkin alapinnan alle jätettävä väli
_HEADROOM_CELL = 200.0       # mm — solun koko jänteen suunnassa
_HEADROOM_HALF = 150.0       # mm — puolileveys footprintille tarkistuksessa
_HEADROOM_MIN_PTS = 8        # solu "tukossa" jos alla väh. tämä pistemäärä
_HEADROOM_MAX_BLOCKED = 0.5  # yli tämän osuus tukossa → ei palkki


def detect_beams(cloud, walls, floor_z: float, ceiling_z: float,
                 has_ceiling: bool = False) -> list[Beam]:
    """Pipeline-entrypoint: palkit kattovyöhykkeestä seinäeksluusiolla.

    has_ceiling=True (valmis tila, KATTOLAATTA löydetty): rajaa palkit SOFFIT-
    vyöhykkeelle (katon alapinnan alta _SOFFIT_BAND) → katosta syvemmälle roikkuva
    talotekniikka (putket/kanavat/kaapelihyllyt) ei mene palkiksi. has_ceiling=False
    (työmaa, ei kattolaattaa): ceiling_z on vain seinänlakikorkeuden varasija, joten
    soffit-rajaus katkoisi aidot palkit → pidetään leveä ylä-puolikaskaista."""
    from .column_detector import _dist_to_walls

    pts = np.asarray(cloud.points)
    if len(pts) < _MIN_INLIERS or ceiling_z - floor_z < 1500.0:
        return []
    band_lo = floor_z + 0.5 * (ceiling_z - floor_z)
    if has_ceiling:
        band_lo = max(band_lo, ceiling_z - _SOFFIT_BAND)
    zmask = (pts[:, 2] > band_lo) & (pts[:, 2] < ceiling_z - 30.0)
    band = pts[zmask]
    if len(band) < _MIN_INLIERS:
        return []
    far = _dist_to_walls(band[:, :2], walls) > _BEAM_WALL_MARGIN
    free = band[far]
    if len(free) < _MIN_INLIERS:
        return []
    sub = o3d.geometry.PointCloud()
    sub.points = o3d.utility.Vector3dVector(free)
    beams, _ = BeamDetector(
        sub_ceiling_mm=float(free[:, 2].max() - free[:, 2].min()) + 100.0,
        ceiling_z=ceiling_z if has_ceiling else None,
    ).detect(sub)
    if has_ceiling:
        beams = [b for b in beams if _has_headroom(b, pts, floor_z)]
    for i, b in enumerate(beams):
        beams[i] = b.model_copy(update={"id": f"beam_{i:03d}"})
    return beams


def _has_headroom(beam, pts: np.ndarray, floor_z: float) -> bool:
    """True jos palkin alapuolella keskikorkeudella on tyhjää (aito palkki).
    Jakaa jänteen soluihin ja katsoo montako on 'tukossa' (pisteitä suoraan alla)."""
    a = np.array(beam.axis[0][:2], dtype=float)
    b = np.array(beam.axis[1][:2], dtype=float)
    seg = b - a
    L = float(np.hypot(*seg))
    if L < _HEADROOM_CELL:
        return True
    dirv = seg / L
    perp = np.array([-dirv[1], dirv[0]])
    z_beam_bottom = float(beam.axis[0][2]) - beam.profile.height / 2.0
    z_hi = z_beam_bottom - _HEADROOM_GAP
    z_lo = floor_z + _HEADROOM_LO
    if z_hi - z_lo < 300.0:              # ei mielekästä alatilaa → älä hylkää
        return True
    rel = pts[:, :2] - a
    t = rel @ dirv
    n = rel @ perp
    below = (
        (pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)
        & (np.abs(n) < _HEADROOM_HALF)
        & (t > 0.2 * L) & (t < 0.8 * L)      # keskimmäinen 60 % jänteestä
    )
    if not below.any():
        return True
    tb = t[below]
    ncells = max(int(0.6 * L / _HEADROOM_CELL), 1)
    cell = np.clip(((tb - 0.2 * L) / _HEADROOM_CELL).astype(np.int64), 0, ncells - 1)
    blocked = np.bincount(cell, minlength=ncells) >= _HEADROOM_MIN_PTS
    return blocked.sum() / ncells <= _HEADROOM_MAX_BLOCKED


class BeamDetector(ElementDetector):
    """Löytää palkit kattovyöhykkeen pitkänomaisista klustereista."""

    def __init__(
        self,
        sub_ceiling_mm: float = 700.0,   # kuinka syvältä katosta etsitään
        eps_mm: float = 80.0,
        min_points: int = 20,
        ceiling_z: float | None = None,  # jos tiedossa (valmis tila) → soffit-kiinnitystesti
    ) -> None:
        self.sub_ceiling_mm = sub_ceiling_mm
        self.eps_mm = eps_mm
        self.min_points = min_points
        self.ceiling_z = ceiling_z

    def detect(
        self,
        cloud: o3d.geometry.PointCloud,
    ) -> tuple[list[Beam], o3d.geometry.PointCloud]:
        pts = np.asarray(cloud.points)
        if len(pts) < self.min_points:
            return [], cloud

        z_max = float(pts[:, 2].max())
        z_lo = z_max - self.sub_ceiling_mm
        z_hi = z_max - 30.0

        zone_mask = (pts[:, 2] >= z_lo) & (pts[:, 2] < z_hi)
        zone_pts = pts[zone_mask]
        zone_idx = np.where(zone_mask)[0]

        if len(zone_pts) < self.min_points:
            return [], cloud

        # Iso kattovyöhyke kaataisi DBSCANin — harvennetaan klusterointiin.
        # Harvennettaessa luovutaan tarkasta inlier-poistosta (palkkeja on vähän;
        # niiden pisteet jäävät krääsälaskentaan, mikä on vaaratonta).
        downsampled = len(zone_pts) > 120_000
        if downsampled:
            from .wall_detector import _downsample_to_target
            zc = o3d.geometry.PointCloud()
            zc.points = o3d.utility.Vector3dVector(zone_pts)
            cluster_src = np.asarray(
                _downsample_to_target(zc, target=120_000, start_voxel=max(self.eps_mm * 0.7, 50.0)).points
            )
        else:
            cluster_src = zone_pts

        zone_2d = cluster_src.copy()
        zone_2d[:, 2] = 0.0
        cloud_2d = o3d.geometry.PointCloud()
        cloud_2d.points = o3d.utility.Vector3dVector(zone_2d)
        labels = np.asarray(cloud_2d.cluster_dbscan(
            eps=self.eps_mm,
            min_points=self.min_points,
            print_progress=False,
        ))

        beams: list[Beam] = []
        beam_labels: set[int] = set()

        for label in set(labels.tolist()):
            if label == -1:
                continue
            cluster = cluster_src[labels == label]
            beam = self._cluster_to_beam(cluster, label)
            if beam is not None:
                beams.append(beam)
                beam_labels.add(label)

        if downsampled:
            # Indeksit eivät vastaa täyttä pilveä → ei tarkkaa poistoa
            return beams, cloud

        # Poista palkki-inlierit alkuperäisestä pilvestä
        beam_zone_inlier_idx = zone_idx[np.isin(labels, list(beam_labels))]
        keep = np.ones(len(pts), dtype=bool)
        keep[beam_zone_inlier_idx] = False
        remaining = o3d.geometry.PointCloud()
        remaining.points = o3d.utility.Vector3dVector(pts[keep])

        log.info("BeamDetector: %d palkkia, %d pistettä jäljellä",
                 len(beams), int(keep.sum()))
        return beams, remaining

    # ------------------------------------------------------------------ #

    def _cluster_to_beam(self, pts: np.ndarray, label: int) -> Beam | None:
        if len(pts) < _MIN_INLIERS:
            return None

        xy = pts[:, :2]
        center_xy = xy.mean(axis=0)
        cov = np.cov((xy - center_xy).T)
        _, eigvecs = np.linalg.eigh(cov)
        axis_dir = eigvecs[:, -1]

        proj = (xy - center_xy) @ axis_dir
        length = float(proj.max() - proj.min())
        if length < _MIN_LENGTH_MM:
            return None

        perp = eigvecs[:, 0]
        width = float(((xy - center_xy) @ perp).ptp())
        if width > _MAX_WIDTH_MM or width < 10:
            return None

        if length / (width + 1e-6) < _MIN_ASPECT:
            return None

        z_depth = float(pts[:, 2].ptp())
        if z_depth < _MIN_HEIGHT_MM:
            return None

        # SOFFIT-KIINNITYS + OHUUS (vain valmis tila, kattolaatta tiedossa):
        # aito alaslaskettu palkki ulottuu kattoon asti eikä ole hiuksenohut.
        # Jos klusterin lakipiste jää katosta yli _SOFFIT_ATTACH_MM alas → se
        # roikkuu irti = talotekniikka (putki/kanava/kaapelihylly), ei palkki.
        # Kattoon kiinnittynyt ohut pitkänomainen (leveys < min) = putki/kouru.
        if self.ceiling_z is not None:
            if float(pts[:, 2].max()) < self.ceiling_z - _SOFFIT_ATTACH_MM:
                return None
            if width < _FINISHED_MIN_WIDTH_MM:
                return None

        # Päätepisteet
        p0_xy = center_xy + proj.min() * axis_dir
        p1_xy = center_xy + proj.max() * axis_dir
        z_mid = float(pts[:, 2].mean())

        profile = BeamProfile(width=round(width, 1), height=round(z_depth, 1))
        confidence = round(min(1.0, len(pts) / 1500.0), 3)

        return Beam(
            id=str(uuid.uuid4()),
            confidence=confidence,
            source=ElementSource(method="cluster", plane_ids=[label]),
            axis=[
                [round(float(p0_xy[0]), 1), round(float(p0_xy[1]), 1), round(z_mid, 1)],
                [round(float(p1_xy[0]), 1), round(float(p1_xy[1]), 1), round(z_mid, 1)],
            ],
            profile=profile,
        )

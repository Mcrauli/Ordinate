"""Semanttinen suodatin (Vaihe 2): poista kalusteet/krääsä ennen geometrista putkea.

Step 1 — PIIRRE-POHJAINEN, EI koulutusdataa, CPU-nopea, deployattava exe:hen.
Pisteytä jokainen piste "rakenne-vs-paska" geometrisilla piirteillä:

  RAKENNE (pidä):
    - SEINÄ:  pystysuora pinta (normaali ~vaakatasossa) JA pisteen (x,y)-pylväs
              ulottuu suuressa osassa lattia→katto-korkeutta (kuten _vertical_mask
              mutta per-piste). Kaluste on osakorkuinen → pylväs-tuki matala → pois.
    - LAATTA: vaakapinta (normaali ~pysty) lattia- tai kattotason lähellä.
  PASKA (pudota):
    - kaikki muu: pöydät, tuolit, sängyt, jääkaapit, hyllyt (osa), irtokrääsä.

Rajapinta: SemanticFilter().filter(cloud) -> cloud (vain rakenteelliset pisteet).
Arkkitehtuuri tukee oppivan mallin vaihtoa myöhemmin (Step 2, S3DIS bookcase/clutter).

HUOM Step 1 -raja: lattia-katto-korkuiset HYLLYT (pystysuora pinta + täysi pylväs)
voivat osin läpäistä → ne vaativat oppivan mallin (Step 2). Suodattaa silti
valtaosan kalusteista.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

# --- parametrit (mm) -------------------------------------------------------
_VOXEL = 18.0              # mm — työ-voxel (normaalit + nopeus)
_NORMAL_RADIUS = 60.0      # mm — normaalin estimointisäde
_NORMAL_NN = 30            # max naapuria normaalille
_VERT_WALL = 0.70          # 1-|nz| >= tämä → pystysuora pinta (seinäkandidaatti)
_HORIZ_SLAB = 0.80         # |nz| >= tämä → vaakapinta (laattakandidaatti)
_SLAB_BAND = 220.0         # mm — laatta hyväksytään näin lähellä lattia/katto-tasoa
_CELL = 60.0               # mm — 2D-soluverkko pylvästuelle
_VSLICE_STEP = 150.0       # mm — pystyviipale pylvästuen laskentaan
_VSLICE_BOTTOM = 350.0     # mm — pylvästuki lasketaan lattia+pohja → katto−ylä
_VSLICE_TOP = 250.0
_COL_FRAC = 0.50           # pylväs-tuki: pikselin täytyttävä näin suuressa osassa viipaleita
_VSLICE_MIN_PER = 1        # min pistettä solussa per viipale → viipale "täynnä"


class SemanticFilter:
    """Geometrinen rakenne/kaluste-suodatin (Step 1, label-vapaa)."""

    def __init__(self, voxel: float = _VOXEL) -> None:
        self.voxel = voxel

    def filter(self, cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
        pts_full = np.asarray(cloud.points)
        if len(pts_full) < 1000:
            return cloud

        # 1) työ-voxel (normaalit + nopeus); maski siirretään takaisin voxel-grid-hashilla
        origin = pts_full.min(axis=0)
        work = cloud.voxel_down_sample(self.voxel)
        wpts = np.asarray(work.points)
        if len(wpts) < 500:
            return cloud

        z = wpts[:, 2]
        floor_z, ceil_z = self._floor_ceiling(z)
        span = ceil_z - floor_z
        if span < 1500.0:
            return cloud  # epäuskottava korkeus → älä suodata

        # 2) normaalit → verticaliteetti
        work.estimate_normals(
            o3d.geometry.KDTreeSearchParamHybrid(radius=_NORMAL_RADIUS, max_nn=_NORMAL_NN))
        nz = np.abs(np.asarray(work.normals)[:, 2])
        vert = 1.0 - nz                       # 1 = pystypinta, 0 = vaakapinta

        # 3) pylväs-tuki: 2D-solu täynnä isossa osassa pystyviipaleita (= ulottuu korkeaksi)
        col_frac = self._column_support(wpts, floor_z, ceil_z)

        # 4) luokittelu
        keep_wall = (vert >= _VERT_WALL) & (col_frac >= _COL_FRAC)
        near_floor = np.abs(z - floor_z) <= _SLAB_BAND
        near_ceil = np.abs(z - ceil_z) <= _SLAB_BAND
        keep_slab = (nz >= _HORIZ_SLAB) & (near_floor | near_ceil)
        keep = keep_wall | keep_slab

        if keep.sum() < 200:
            return cloud

        # 5) siirrä maski TÄYDELLE pilvelle voxel-grid-hashilla (vektoroitu, nopea):
        # piste säilyy jos sen voxel oli säilytetyssä työ-voxelissa.
        def _vkey(p):
            v = np.floor((p - origin) / self.voxel).astype(np.int64)
            # litistä 3D-indeksi yhdeksi int64-avaimeksi (riittävä alue sisätilalle)
            return (v[:, 0] * 100003 + v[:, 1]) * 100003 + v[:, 2]
        kept_keys = np.unique(_vkey(wpts[keep]))
        full_keys = _vkey(pts_full)
        keep_full = np.isin(full_keys, kept_keys)
        return cloud.select_by_index(np.where(keep_full)[0])

    # --- apurit ------------------------------------------------------------

    @staticmethod
    def _floor_ceiling(z: np.ndarray) -> tuple[float, float]:
        hist, edges = np.histogram(z, bins=200)
        centers = 0.5 * (edges[:-1] + edges[1:])
        thr = 0.25 * float(hist.max())
        strong = np.where(hist >= thr)[0]
        if len(strong) < 2:
            return float(z.min()), float(z.max())
        return float(centers[strong[0]]), float(centers[strong[-1]])

    @staticmethod
    def _column_support(pts: np.ndarray, floor_z: float, ceil_z: float) -> np.ndarray:
        """Per piste: kuinka suuressa osassa pystyviipaleita sen (x,y)-solu on täynnä."""
        xy = pts[:, :2]
        z = pts[:, 2]
        x0, y0 = xy[:, 0].min(), xy[:, 1].min()
        ix = ((xy[:, 0] - x0) / _CELL).astype(np.int64)
        iy = ((xy[:, 1] - y0) / _CELL).astype(np.int64)
        ncx = int(ix.max()) + 1
        cell_id = ix * (int(iy.max()) + 1) + iy   # litistetty soluindeksi

        z0 = floor_z + _VSLICE_BOTTOM
        z1 = ceil_z - _VSLICE_TOP
        n_sl = max(int((z1 - z0) / _VSLICE_STEP), 1)

        # per solu: montako eri pystyviipaletta sisältää pisteitä (vektoroitu)
        sl = np.clip(((z - z0) / _VSLICE_STEP).astype(np.int64), 0, n_sl - 1)
        inband = (z >= z0) & (z <= z1)
        ncell = int(cell_id.max()) + 1
        # uniikit (solu, viipale)-parit → montako viipaletta per solu
        pair = cell_id[inband].astype(np.int64) * n_sl + sl[inband]
        uniq_pairs = np.unique(pair)
        cells_u = uniq_pairs // n_sl
        counts = np.bincount(cells_u, minlength=ncell)
        return counts[cell_id] / float(n_sl)

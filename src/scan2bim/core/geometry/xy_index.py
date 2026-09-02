"""XY-ruutuindeksi seinäkohtaisiin pistehakuihin.

Geometriaketjun vaiheet (`_trim_endpoints`, `_surface_lock_wall`,
`_thickness_lock_wall`, `_align_faces_to_surface_median`, `refine_thicknesses`)
laskevat jokaiselle seinälle projektiot KOKO pistetaulukolle ja poimivat sitten
kapean kaistan. Työ on siis O(seinät × pisteet) vaikka kaista on murto-osa
pilvestä: profiloitu 72×48 m myymälällä (8.2 M pistettä, 165 seinää) —
`_trim_endpoints` 41 s ja `_surface_lock_wall` 38 s, koko ketju ~159 s.

Indeksi palauttaa YLIJOUKON kaistan pisteistä (ruudun tarkkuudella), ja kutsuja
soveltaa saman ehdon kuin ennenkin → valikoituva pistejoukko on täsmälleen sama.
Indeksit palautetaan nousevassa järjestyksessä, joten myös pisteiden JÄRJESTYS
säilyy — percentiilit, histogrammit ja mediaanit antavat bitilleen saman arvon.
"""
from __future__ import annotations

import numpy as np

_CELL_MM = 1000.0
_HALF_DIAG = 0.70711        # ruudun puolikas lävistäjä / ruudun sivu


class XYIndex:
    """Miehitetyt XY-ruudut ja niiden pisteindeksit."""

    __slots__ = ("_origin", "_cell", "_order", "_starts", "_ends", "_cx", "_cy", "_n")

    def __init__(self, pts: np.ndarray, cell: float = _CELL_MM) -> None:
        xy = np.asarray(pts)[:, :2]
        self._n = len(xy)
        self._cell = float(cell)
        if self._n == 0:
            self._origin = np.zeros(2)
            self._order = np.empty(0, dtype=np.int64)
            self._starts = self._ends = np.empty(0, dtype=np.int64)
            self._cx = self._cy = np.empty(0)
            return
        self._origin = xy.min(axis=0)
        g = np.floor((xy - self._origin) / self._cell).astype(np.int64)
        ny = int(g[:, 1].max()) + 1
        key = g[:, 0] * ny + g[:, 1]
        self._order = np.argsort(key, kind="stable")
        ks = key[self._order]
        uniq, starts = np.unique(ks, return_index=True)
        self._starts = starts
        self._ends = np.append(starts[1:], len(ks))
        self._cx = self._origin[0] + (uniq // ny + 0.5) * self._cell
        self._cy = self._origin[1] + (uniq % ny + 0.5) * self._cell

    def near_segment(self, p0, along, normal, radius: float,
                     s_lo: float = -np.inf, s_hi: float = np.inf) -> np.ndarray:
        """Pisteindeksit joiden ruutu voi osua kaistaan.

        ``radius`` = kohtisuora etäisyys akselista; ``s_lo``/``s_hi`` = rajaus
        akselin suunnassa (±inf = ei rajausta). Palauttaa nousevan indeksitaulun.
        """
        if self._n == 0 or len(self._starts) == 0:
            return np.empty(0, dtype=np.int64)
        pad = _HALF_DIAG * self._cell
        dx = self._cx - float(p0[0])
        dy = self._cy - float(p0[1])
        sel = np.abs(dx * normal[0] + dy * normal[1]) <= radius + pad
        if np.isfinite(s_lo) or np.isfinite(s_hi):
            s = dx * along[0] + dy * along[1]
            if np.isfinite(s_lo):
                sel &= s >= s_lo - pad
            if np.isfinite(s_hi):
                sel &= s <= s_hi + pad
        if not sel.any():
            return np.empty(0, dtype=np.int64)
        parts = [self._order[a:b] for a, b in zip(self._starts[sel], self._ends[sel])]
        idx = np.concatenate(parts)
        idx.sort()
        return idx


def subset(pts: np.ndarray, index: "XYIndex | None", p0, along, normal,
           radius: float, s_lo: float = -np.inf, s_hi: float = np.inf):
    """(osajoukko, indeksit) — ilman indeksiä palautetaan koko taulukko."""
    if index is None:
        return pts, None
    idx = index.near_segment(p0, along, normal, radius, s_lo, s_hi)
    return pts[idx], idx


# --- Indeksin välimuisti -----------------------------------------------------
# Sama pilvi indeksoidaan ketjussa yhä uudelleen: `_recenter_wall_axes` (4×),
# `_trim_wall_endpoints` (2×), `_thickness_lock_walls`, `_align_faces...`,
# `refine_thicknesses`, `measure_wall_support` (9×), `snap_displaced_walls`.
# Profiloitu koulun kellarilla: 22 rakennusta, 187.8 s = 16 % koko ajosta,
# ja siitä lähes kaikki on argsort 45 M pisteen taulukolle.
#
# Välimuisti on TULOSNEUTRAALI: sama pilvi antaa saman indeksin, joten
# osajoukot ja niiden JÄRJESTYS ovat täsmälleen samat kuin ennen.
#
# Avain on pilviolion identiteetti, ja pilvi pidetään hengissä arvossa jottei
# id() voi kierrättyä toiselle oliolle. Pistemäärä tarkistetaan varmuuden
# vuoksi: jos pilveä on muokattu paikallaan, indeksi rakennetaan uudelleen.
_CACHE: dict[int, tuple[object, int, "XYIndex"]] = {}


def index_for(cloud, pts: np.ndarray) -> "XYIndex":
    """Pilven XY-indeksi välimuistista; rakennetaan kerran per pilvi."""
    key = id(cloud)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] is cloud and hit[1] == len(pts):
        return hit[2]
    index = XYIndex(pts)
    _CACHE[key] = (cloud, len(pts), index)
    return index


def clear_index_cache() -> None:
    """Vapauta indeksit ja niiden pitämät pilviviitteet (kerroksen lopussa)."""
    _CACHE.clear()

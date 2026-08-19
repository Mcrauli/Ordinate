"""Z-histogrammipohjainen kerrosjako: etsi oikeasti tyhjät kaistat (laattavälit)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


_MIN_FLOOR_HEIGHT = 2000.0   # mm
_Z_BIN_MM = 25.0             # mm — pienet binit, jotta laattavälin sisäosa on aidosti tyhjä
_MIN_GAP_MM = 150.0          # mm — gap-kaistan minimipituus kerrosjaoksi
_Z_BUFFER = 200.0            # mm — puskuri kerroksen ylä/alarajalle
_MIN_FLOOR_FRAC = 0.02       # kerroksessa oltava ≥ 2 % pisteistä (aito parvikin ≥3–5 %; (harhapisteet
                             # scene_02008: haamu oli 0.07 %) — harha ei ole kerros
_TALL_SPAN_MM = 4600.0       # tätä korkeampi viipale voi sisältää 2 tasoa
_SLAB_PEAK_FRAC = 0.30       # laattapiikin min-korkeus (osuus maksimista)
_SLAB_GROUP_MM = 600.0       # piikit tämän sisällä = sama laatta (kaksi pintaa)
_SLAB_OVERLAP = 300.0        # jaetun laatan molemmat puolet saavat laatan evidenssin
_SLAB_PAIR_MIN = 100.0       # kerrosjako vaatii PINTAPARIN: alemman kerroksen katto JA
_SLAB_PAIR_MAX = 600.0
_SLAB_PAIR_EMPTY = 0.15      # osuus ryhman huipusta: tama alittava bini on umpibetonia       # ylemman lattia. Yksi vaakapinta on palkiston alapinta tai
                             # parven reuna, ei kerrosjako. Mitattu: aito jako
                             # (test_multiscan) 3000 + 3296 = 296 mm, Rohbau site_07:n
                             # palkiston alapinta 5450 yksin. Kolme muuta ehdokasta
                             # (jalanjaljen peitto, pisteet ylapuolella, kavelytaso)
                             # kumoutuivat mittauksessa - ks. AGENTS.md


def _is_slab_pair(group: list[float], centers: np.ndarray, hist: np.ndarray) -> bool:
    """Onko piikkiryhma kaksi pintaa joiden valissa on umpinaista rakennetta.

    Betoni ei palauta pistetta, joten laatan alapinnan ja ylapinnan valissa on
    aidosti tyhja kaista. Palkiston alapinta on yksi pinta jonka hajonta voi
    olla saman levyinen — mutta sen sisalla on pisteita joka binissa.
    Tyhjyys mitataan OSUUTENA ryhman omasta huipusta, ei pistemaarana, jotta
    saanto ei muutu skannin tiheyden mukana.
    """
    lo, hi = min(group), max(group)
    if not (_SLAB_PAIR_MIN <= hi - lo <= _SLAB_PAIR_MAX):
        return False
    inner = hist[(centers > lo) & (centers < hi)]
    if not len(inner):
        return False
    peak = float(hist[(centers >= lo) & (centers <= hi)].max())
    return bool((inner <= _SLAB_PAIR_EMPTY * peak).any())


def detect_floors(z: np.ndarray) -> list[tuple[float, float]]:
    """
    Tunnistaa kerrokset etsimällä oikeasti tyhjiä Z-kaistoja.

    Algoritmit:
      1. 25mm-histogrammi ilman tasoitusta
      2. Binit joissa pisteitä <= 0.02 % kokonaispisteistä = "tyhjä" (sallii pienen kohinaspillin)
      3. Yhtenäiset tyhjäkaistat >= 150mm = kerrosväli
      4. Kerrosvälin keskikohta = jakoraja

    Toimii sekä:
      - Synteettisellä datalla (täydellinen gap, hist==0)
      - Todellisella skannauksella (lattia/katto-pinnat erittäin tiheitä, mutta laatan sisus tyhjä)
    """
    z_min, z_max = float(z.min()), float(z.max())
    total_span = z_max - z_min
    if total_span < _MIN_FLOOR_HEIGHT:
        return [(z_min - _Z_BUFFER, z_max + _Z_BUFFER)]

    n_bins = max(int(total_span / _Z_BIN_MM), 8)
    hist, edges = np.histogram(z, bins=n_bins, range=[z_min, z_max])

    # Tyhjyyskynnys: alle 0.02 % kokonaispisteistä per bin
    # Tämä sallii minimaalisen kohinaspillin laatan reunalla mutta tunnistaa laatan sisuksen tyhjäksi
    empty_thr = max(int(len(z) * 0.0002), 2)
    is_empty = hist <= empty_thr

    # Etsi yhtenäiset tyhjäkaistat
    min_gap_bins = max(int(_MIN_GAP_MM / _Z_BIN_MM), 3)
    splits: list[float] = []
    gap_start: int | None = None

    for i, empty in enumerate(is_empty):
        if empty and gap_start is None:
            gap_start = i
        elif not empty and gap_start is not None:
            if (i - gap_start) >= min_gap_bins:
                splits.append((float(edges[gap_start]) + float(edges[i])) / 2.0)
            gap_start = None
    if gap_start is not None and (n_bins - gap_start) >= min_gap_bins:
        splits.append((float(edges[gap_start]) + z_max) / 2.0)

    floors: list[tuple[float, float]] = []
    prev = z_min
    for sp in splits:
        if sp - prev >= _MIN_FLOOR_HEIGHT:
            floors.append((prev - _Z_BUFFER, sp + _Z_BUFFER))
        prev = sp
    if z_max - prev >= _MIN_FLOOR_HEIGHT:
        floors.append((prev - _Z_BUFFER, z_max + _Z_BUFFER))
    if not floors:
        floors = [(z_min - _Z_BUFFER, z_max + _Z_BUFFER)]

    # Harhapistesuodatin: "kerros" jossa on alle 1 % pisteistä on skannerin
    # haamuja rakennuksen ala/yläpuolella — tuottaisi tyhjän mallin IFC:hen.
    counted = [(lo, hi, int(((z >= lo) & (z <= hi)).sum())) for lo, hi in floors]
    floors = [(lo, hi) for lo, hi, n in counted if n >= _MIN_FLOOR_FRAC * len(z)]
    if not floors:
        floors = [max(counted, key=lambda t: t[2])[:2]]

    # Korkea viipale ilman tyhjää kaistaa voi sisältää KAKSI tasoa (portaikko/
    # aukot yhdistävät → laattaväli ei ole tyhjä). Jaa sisäisen laattapiikin
    # kohdalta; molemmat puolet saavat laatan evidenssin (±_SLAB_OVERLAP).
    out: list[tuple[float, float]] = []
    for lo, hi in floors:
        out.extend(_split_tall_slice(z, lo, hi))
    return out


def _split_tall_slice(z: np.ndarray, lo: float, hi: float) -> list[tuple[float, float]]:
    if hi - lo < _TALL_SPAN_MM:
        return [(lo, hi)]
    zz = z[(z >= lo) & (z <= hi)]
    if len(zz) < 1000:
        return [(lo, hi)]
    nb = max(int((hi - lo) / 100.0), 10)
    hist, edges = np.histogram(zz, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    strong = centers[hist >= _SLAB_PEAK_FRAC * hist.max()]
    if len(strong) == 0:
        return [(lo, hi)]
    # ryhmittele piikit laatoiksi
    groups: list[list[float]] = [[float(strong[0])]]
    for c in strong[1:]:
        if c - groups[-1][-1] <= _SLAB_GROUP_MM:
            groups[-1].append(float(c))
        else:
            groups.append([float(c)])
    # Kerrosjako vaatii pintaparin (katto + lattia) JA niiden valissa betonin.
    # Pelkka levays ei erota parin yhdesta paksusta pinnasta: mitattu
    # scene_07000, palkiston alapinta z 5363..5563 — levays 200 mm eli "pari",
    # mutta sen sisalla ei ole yhtaan tyhjaa binia. Aidon laatan sisalla on:
    # alapinta, umpibetoni, ylapinta. Ilman tyhjyysehtoa jako oli kiinni
    # TIHEYDESSA: sama scene jakautui kahteen kerrokseen voxeleilla 20 ja 40
    # mutta ei voxeleilla 0, 10 ja 80.
    slabs = [float(np.mean(g)) for g in groups
             if _is_slab_pair(g, centers, hist)
             or g is groups[0] or g is groups[-1]]
    if len(slabs) < 3:
        return [(lo, hi)]
    # sisäiset laatat = jakokohdat; hylkää jako joka tuottaisi <2m tason
    result: list[tuple[float, float]] = []
    seg_lo = lo
    for s in slabs[1:-1]:
        if s - seg_lo >= _MIN_FLOOR_HEIGHT and hi - s >= _MIN_FLOOR_HEIGHT:
            result.append((seg_lo, s + _SLAB_OVERLAP))
            seg_lo = s - _SLAB_OVERLAP
    result.append((seg_lo, hi))
    return result if len(result) > 1 else [(lo, hi)]


def detect_floors_from_files(paths: list[Path], sample_step: int = 1) -> list[tuple[float, float]]:
    """Käy tiedostot läpi, kerää vain Z-koordinaatit, tunnistaa kerrokset."""
    from scan2bim.core.geometry.loader import (
        load_point_cloud, read_ply_z, ply_autoscale_factor, read_e57_z,
        _e57_is_chunkable,
    )
    all_z: list[np.ndarray] = []
    for path in paths[::max(sample_step, 1)]:
        # Iso binääri-PLY: vain Z lohkoluvulla + desimointi, ei koko tiedostoa muistiin.
        if path.suffix.lower() == ".ply":
            try:
                z = read_ply_z(path)
                if z is not None and len(z) > 0:
                    all_z.append(z * ply_autoscale_factor(path))
                    continue
            except Exception:
                pass
        # E57 samoin: read_scan varaisi koko skannin, ja iso keilaus on yksi skanni.
        elif path.suffix.lower() == ".e57" and _e57_is_chunkable(path):
            try:
                z = read_e57_z(path)
                if z is not None and len(z) > 0:
                    all_z.append(z)
                    continue
            except Exception:
                pass
        try:
            cloud = load_point_cloud(path)
        except Exception:
            continue
        pts = np.asarray(cloud.points)
        if len(pts) > 0:
            all_z.append(pts[:, 2].astype(np.float32))
        del cloud
    if not all_z:
        return [(0.0, 3000.0)]
    return detect_floors(np.concatenate(all_z))

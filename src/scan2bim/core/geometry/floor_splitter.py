"""Z-histogrammipohjainen kerrosjako: etsi oikeasti tyhjät kaistat (laattavälit)."""
from __future__ import annotations

from pathlib import Path

import numpy as np


_MIN_FLOOR_HEIGHT = 2000.0   # mm
_Z_BIN_MM = 25.0             # mm — pienet binit, jotta laattavälin sisäosa on aidosti tyhjä
_MIN_GAP_MM = 150.0          # mm — gap-kaistan minimipituus kerrosjaoksi
_Z_BUFFER = 200.0            # mm — puskuri kerroksen ylä/alarajalle


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

    if not splits:
        return [(z_min - _Z_BUFFER, z_max + _Z_BUFFER)]

    floors: list[tuple[float, float]] = []
    prev = z_min
    for sp in splits:
        if sp - prev >= _MIN_FLOOR_HEIGHT:
            floors.append((prev - _Z_BUFFER, sp + _Z_BUFFER))
        prev = sp
    if z_max - prev >= _MIN_FLOOR_HEIGHT:
        floors.append((prev - _Z_BUFFER, z_max + _Z_BUFFER))

    return floors if floors else [(z_min - _Z_BUFFER, z_max + _Z_BUFFER)]


def detect_floors_from_files(paths: list[Path], sample_step: int = 1) -> list[tuple[float, float]]:
    """Käy tiedostot läpi, kerää vain Z-koordinaatit, tunnistaa kerrokset."""
    from scan2bim.core.geometry.loader import load_point_cloud
    all_z: list[np.ndarray] = []
    for path in paths[::max(sample_step, 1)]:
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

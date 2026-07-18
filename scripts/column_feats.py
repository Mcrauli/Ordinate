"""Pystyjatkuvuuspiirteet per piste — XYZ-only, lisenssivapaa.

Koodaa verkolle sen domain-havainnon jolla geometrinen suodatin jo toimii
(wall_contour._vertical_mask): seina ulottuu lattiasta kattoon, osakorkuinen
kaluste ei. Verkko nakee vain 1 m lohkon eika voi paatella tata itse.

Palauttaa (N,3): [col_fill, col_span, z_rel]
  col_fill = tayttyneiden z-binien osuus pisteen XY-sarakkeessa (0-1)
  col_span = sarakkeen korkeus / skenen korkeus (0-1)
  z_rel    = pisteen korkeus lattiasta / skenen korkeus (0-1)
"""
import numpy as np

CELL_M = 0.10          # XY-ruutu (vastaa vertical_mask-tiheytta)
Z_BIN_M = 0.20         # pystybinin korkeus


def compute(xyz: np.ndarray, cell_m: float = CELL_M, z_bin_m: float = Z_BIN_M) -> np.ndarray:
    xyz = np.ascontiguousarray(xyz[:, :3].astype(np.float64))
    n = len(xyz)
    if n < 8:
        return np.zeros((n, 3), np.float32)
    lo = xyz.min(axis=0)
    z_lo, z_hi = np.percentile(xyz[:, 2], 1), np.percentile(xyz[:, 2], 99)
    z_h = max(z_hi - z_lo, 1e-6)

    gx = np.floor((xyz[:, 0] - lo[0]) / cell_m).astype(np.int64)
    gy = np.floor((xyz[:, 1] - lo[1]) / cell_m).astype(np.int64)
    gz = np.clip(np.floor((xyz[:, 2] - z_lo) / z_bin_m).astype(np.int64), 0, None)
    nz = int(gz.max()) + 1

    # sarake-id per piste
    ny = int(gy.max()) + 1
    col = gx * ny + gy
    ucol, cinv = np.unique(col, return_inverse=True)

    # tayttyneet z-binit per sarake: uniikit (sarake, z)-parit
    pair = cinv.astype(np.int64) * nz + gz
    upair = np.unique(pair)
    filled = np.bincount(upair // nz, minlength=len(ucol)).astype(np.float32)

    # sarakkeen z-ulottuvuus
    zmax = np.full(len(ucol), -np.inf); zmin = np.full(len(ucol), np.inf)
    np.maximum.at(zmax, cinv, xyz[:, 2]); np.minimum.at(zmin, cinv, xyz[:, 2])

    col_fill = np.clip(filled / max(nz, 1), 0.0, 1.0)[cinv]
    col_span = np.clip((zmax - zmin) / z_h, 0.0, 1.0)[cinv]
    z_rel = np.clip((xyz[:, 2] - z_lo) / z_h, 0.0, 1.0)

    return np.column_stack([col_fill, col_span, z_rel]).astype(np.float32)

"""Per-point features for the semantic filter — license-free, XYZ-only.

The production cloud has no colour (E57 loader never reads it, streaming frees
it), so the newer filter models are trained on geometry alone. This module
rebuilds, at inference time, exactly the feature channels those models were
trained on:

  height      clip((z - floor_z) / 3 m, 0, 1.5)      floor_z = 2nd percentile
  geometric   verticality, planarity, sphericity     local PCA (Weinmann-style)
  column      col_fill, col_span, z_rel              vertical continuity

The column features encode the same domain rule the geometric detector relies
on (``wall_contour._vertical_mask``): a wall spans floor to ceiling, a
part-height cabinet does not. The network sees only a 1 m block and cannot
derive this on its own, so it is supplied as a per-point value computed over
the WHOLE scene.

UNITS: every function here takes coordinates in **millimetres** (the pipeline
convention) and converts internally. Training ran in metres, so the cell sizes
below are the metre constants expressed in mm — do not "simplify" them away.
"""
from __future__ import annotations

import numpy as np

_MM_PER_M = 1000.0

_GEO_K = 16              # kNN neighbourhood; scale-free, so mm vs m is moot here
_CELL_MM = 100.0         # XY cell for the column grid (0.10 m in training)
_Z_BIN_MM = 200.0        # vertical bin height (0.20 m in training)
_HEIGHT_REF_MM = 3000.0  # height normalisation reference (3 m in training)


def height(xyz_mm: np.ndarray) -> np.ndarray:
    """(N,) height above floor, normalised by 3 m and clipped to training range."""
    z = xyz_mm[:, 2]
    floor_z = np.percentile(z, 2)
    return np.clip((z - floor_z) / _HEIGHT_REF_MM, 0.0, 1.5).astype(np.float32)


def geometric(xyz_mm: np.ndarray, k: int = _GEO_K) -> np.ndarray:
    """(N,3) [verticality, planarity, sphericity] from local covariance eigenvalues.

    Ratios of eigenvalues and a normal direction — scale invariant, so the mm
    input needs no conversion.
    """
    from scipy.spatial import cKDTree  # noqa: PLC0415

    xyz = np.ascontiguousarray(xyz_mm[:, :3].astype(np.float64))
    n = len(xyz)
    if n < k + 1:
        return np.zeros((n, 3), np.float32)
    _, idx = cKDTree(xyz).query(xyz, k=k, workers=-1)
    nb = xyz[idx]
    nb = nb - nb.mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / k
    ev, evec = np.linalg.eigh(cov)              # ascending: l3, l2, l1
    l3, l2, l1 = ev[:, 0], ev[:, 1], ev[:, 2]
    l1 = np.maximum(l1, 1e-12)
    out = np.column_stack([
        1.0 - np.abs(evec[:, :, 0][:, 2]),      # verticality from smallest-eigenvalue vector
        (l2 - l3) / l1,                         # planarity
        l3 / l1,                                # sphericity
    ]).astype(np.float32)
    return np.clip(out, 0.0, 1.0)


def column(xyz_mm: np.ndarray) -> np.ndarray:
    """(N,3) [col_fill, col_span, z_rel] — vertical continuity of the XY column.

    Must be computed over the whole scene: a 1 m block cannot tell whether the
    surface it contains continues to the floor and ceiling.
    """
    xyz = np.ascontiguousarray(xyz_mm[:, :3].astype(np.float64))
    n = len(xyz)
    if n < 8:
        return np.zeros((n, 3), np.float32)
    lo = xyz.min(axis=0)
    z_lo, z_hi = np.percentile(xyz[:, 2], 1), np.percentile(xyz[:, 2], 99)
    z_h = max(z_hi - z_lo, 1e-6)

    gx = np.floor((xyz[:, 0] - lo[0]) / _CELL_MM).astype(np.int64)
    gy = np.floor((xyz[:, 1] - lo[1]) / _CELL_MM).astype(np.int64)
    gz = np.clip(np.floor((xyz[:, 2] - z_lo) / _Z_BIN_MM).astype(np.int64), 0, None)
    nz = int(gz.max()) + 1

    ny = int(gy.max()) + 1
    ucol, cinv = np.unique(gx * ny + gy, return_inverse=True)

    # filled bins per column = unique (column, z-bin) pairs
    upair = np.unique(cinv.astype(np.int64) * nz + gz)
    filled = np.bincount(upair // nz, minlength=len(ucol)).astype(np.float32)

    zmax = np.full(len(ucol), -np.inf)
    zmin = np.full(len(ucol), np.inf)
    np.maximum.at(zmax, cinv, xyz[:, 2])
    np.minimum.at(zmin, cinv, xyz[:, 2])

    return np.column_stack([
        np.clip(filled / max(nz, 1), 0.0, 1.0)[cinv],        # col_fill
        np.clip((zmax - zmin) / z_h, 0.0, 1.0)[cinv],        # col_span
        np.clip((xyz[:, 2] - z_lo) / z_h, 0.0, 1.0),         # z_rel
    ]).astype(np.float32)

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
_GEO_CHUNK = 500_000     # query points per batch; caps the neighbour-gather transient
_CELL_MM = 100.0         # XY cell for the column grid (0.10 m in training)
_Z_BIN_MM = 200.0        # vertical bin height (0.20 m in training)
_HEIGHT_REF_MM = 3000.0  # height normalisation reference (3 m in training)
_STORY_MM = 3000.0       # storey reference for the column features (multi-height robust)


def height(xyz_mm: np.ndarray) -> np.ndarray:
    """(N,) height above floor, normalised by 3 m and clipped to training range."""
    z = xyz_mm[:, 2]
    floor_z = np.percentile(z, 2)
    return np.clip((z - floor_z) / _HEIGHT_REF_MM, 0.0, 1.5).astype(np.float32)


def geometric(xyz_mm: np.ndarray, k: int = _GEO_K, chunk: int = _GEO_CHUNK) -> np.ndarray:
    """(N,3) [verticality, planarity, sphericity] from local covariance eigenvalues.

    Ratios of eigenvalues and a normal direction — scale invariant, so the mm
    input needs no conversion.

    Chunked over the query points. The neighbour gather is the whole pipeline's
    memory peak: at k=16 it holds N*k*3 float64 twice (~6 GB at 8 M points), which
    is what a large retail scan hits before anything else. The tree is still built
    once over ALL points, so every neighbourhood — and therefore every output
    value — is bit-identical to the unchunked form; only the transient shrinks.
    """
    from scipy.spatial import cKDTree  # noqa: PLC0415

    xyz = np.ascontiguousarray(xyz_mm[:, :3].astype(np.float64))
    n = len(xyz)
    if n < k + 1:
        return np.zeros((n, 3), np.float32)
    tree = cKDTree(xyz)
    out = np.empty((n, 3), np.float32)
    for lo in range(0, n, chunk):
        hi = min(lo + chunk, n)
        _, idx = tree.query(xyz[lo:hi], k=k, workers=-1)
        nb = xyz[idx]
        nb -= nb.mean(axis=1, keepdims=True)
        cov = np.einsum("nki,nkj->nij", nb, nb) / k
        ev, evec = np.linalg.eigh(cov)          # ascending: l3, l2, l1
        l3, l2, l1 = ev[:, 0], ev[:, 1], ev[:, 2]
        l1 = np.maximum(l1, 1e-12)
        out[lo:hi] = np.clip(np.column_stack([
            1.0 - np.abs(evec[:, :, 0][:, 2]),  # verticality from smallest-eigenvalue vector
            (l2 - l3) / l1,                     # planarity
            l3 / l1,                            # sphericity
        ]), 0.0, 1.0)
    return out


def column(xyz_mm: np.ndarray) -> np.ndarray:
    """(N,3) [col_fill, col_span, z_story] — vertical continuity of the XY column.

    Multi-height robust: all three are measured against the column's OWN local
    floor and a fixed storey reference (3 m), NOT the global scene height.
    Normalising by scene height put an intermediate-level beam in a 6 m space at
    z_rel 0.45 — the training furniture zone — so the filter dropped beams,
    columns and stairs on multi-level scans (Rohbau site_10). Against a local
    floor the same beam reads ~0.8 (ceiling zone) regardless of building height.

    Must be computed over the whole scene: a 1 m block cannot tell whether the
    surface it contains continues to its floor and ceiling.
    """
    xyz = np.ascontiguousarray(xyz_mm[:, :3].astype(np.float64))
    n = len(xyz)
    if n < 8:
        return np.zeros((n, 3), np.float32)
    lo = xyz.min(axis=0)
    z = xyz[:, 2]

    gx = np.floor((xyz[:, 0] - lo[0]) / _CELL_MM).astype(np.int64)
    gy = np.floor((xyz[:, 1] - lo[1]) / _CELL_MM).astype(np.int64)
    gz = np.clip(np.floor((z - lo[2]) / _Z_BIN_MM).astype(np.int64), 0, None)
    nz = int(gz.max()) + 1

    ny = int(gy.max()) + 1
    ucol, cinv = np.unique(gx * ny + gy, return_inverse=True)

    # per-column local floor and ceiling (NOT global scene)
    col_floor = np.full(len(ucol), np.inf)
    col_ceil = np.full(len(ucol), -np.inf)
    np.minimum.at(col_floor, cinv, z)
    np.maximum.at(col_ceil, cinv, z)
    local_h = np.maximum(col_ceil - col_floor, 1e-6)

    # filled bins per column = unique (column, z-bin) pairs
    upair = np.unique(cinv.astype(np.int64) * nz + gz)
    filled = np.bincount(upair // nz, minlength=len(ucol)).astype(np.float64)

    # col_fill uses a FIXED storey-bin count so a flat floor reads ~0, not 1/1
    story_bins = _STORY_MM / _Z_BIN_MM
    return np.column_stack([
        np.clip(filled / story_bins, 0.0, 1.0)[cinv],        # col_fill
        np.clip(local_h / _STORY_MM, 0.0, 1.0)[cinv],        # col_span
        np.clip((z - col_floor[cinv]) / _STORY_MM, 0.0, 1.0),  # z_story
    ]).astype(np.float32)

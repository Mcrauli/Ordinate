"""Onko kerrosjaon tasolla KAVELYTASO.

Aito kerros on tason varassa: ylemman viipaleen soluista valtaosan ALIN piste
on juuri jakotasolla. Keksitty jako (palkiston alapinta) ei kanna mitaan -
ylapuolisen viipaleen alin piste on useimmissa soluissa paljon korkeammalla,
koska palkkien valista nakee suoraan kattoon.

Ajo: _split_floor_probe.py <cloud> <jakotaso> <viipaleen ylaraja>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _soffit_probe import load_pts  # noqa: E402

_CELL = 400.0
_TOL = 300.0


def rests_on(P: np.ndarray, split: float, hi: float) -> tuple[float, int]:
    m = (P[:, 2] > split - 100.0) & (P[:, 2] < hi)
    q = P[m]
    if len(q) < 100:
        return 0.0, 0
    ij = np.floor(q[:, :2] / _CELL).astype(np.int64)
    key = (ij[:, 0] + 500_000) * 1_000_003 + (ij[:, 1] + 500_000)
    order = np.argsort(key, kind="stable")
    k, z = key[order], q[order, 2]
    b = np.flatnonzero(np.diff(k)) + 1
    starts = np.concatenate([[0], b])
    ends = np.concatenate([b, [len(k)]])
    lows = np.array([z[s:e].min() for s, e in zip(starts, ends)])
    n = np.array([e - s for s, e in zip(starts, ends)])
    keep = n >= 3
    lows = lows[keep]
    if not len(lows):
        return 0.0, 0
    return float((lows < split + _TOL).mean()), len(lows)


def main() -> None:
    P = load_pts(sys.argv[1])
    split, hi = float(sys.argv[2]), float(sys.argv[3])
    frac, n = rests_on(P, split, hi)
    print(f"{Path(sys.argv[1]).parent.name:16s} jako {split:7.0f} .. {hi:7.0f}  "
          f"soluja {n:6d}  alin piste jakotasolla {frac:.2f}")


if __name__ == "__main__":
    main()

"""Onko taso VALIPOHJA vai palkiston alapinta.

`_split_tall_slice` valitsee kerrosjaon vaakapiikin SUOSION perusteella, ja
10 m hallissa palkiston alapinta voittaa oikean katon (mitattu: 2.9 M vs
2.8 M pistetta). Jalanjaljen peitto ei erota naita (mitattu, kumoutui).

Tama mittaa fysikaalisen eron: valipohja on PINTAPARI - alapinta ja sen
paalla kavelytaso 150-400 mm ylempana SAMASSA solussa. Palkin alapinnan
yläpuolella on tyhjaa palkin lakeen asti.

Ajo: _slab_pair_probe.py <cloud> <taso> [taso ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _soffit_probe import load_pts  # noqa: E402

_CELL = 400.0
_BAND = 60.0
_LO, _HI = 150.0, 500.0


def stats(P: np.ndarray, z: float) -> dict:
    ij = np.floor(P[:, :2] / _CELL).astype(np.int64)
    key = (ij[:, 0] + 500_000) * 1_000_003 + (ij[:, 1] + 500_000)
    at = np.abs(P[:, 2] - z) < _BAND
    above = (P[:, 2] > z + _LO) & (P[:, 2] < z + _HI)
    below = (P[:, 2] < z - _LO) & (P[:, 2] > z - _HI)
    A = set(key[at].tolist())
    if not A:
        return dict(n=0, pari=0.0, alla=0.0)
    B = set(key[above].tolist())
    C = set(key[below].tolist())
    return dict(n=len(A), pari=len(A & B) / len(A), alla=len(A & C) / len(A))


def main() -> None:
    P = load_pts(sys.argv[1])
    print(f"{Path(sys.argv[1]).parent.name}  n={len(P) / 1e6:.1f}M")
    print(f"{'taso':>8s} {'soluja':>7s} {'paalla 150-500':>15s} {'alla 150-500':>13s}")
    for a in sys.argv[2:]:
        z = float(a)
        s = stats(P, z)
        print(f"{z:8.0f} {s['n']:7d} {s['pari']:15.2f} {s['alla']:13.2f}")


if __name__ == "__main__":
    main()

"""Mihin e57-luvun aika menee ja auttaako rinnakkaisuus?

Kellarin ajosta 64 minuutista 33 on saman 30 GB:n lukemista neljään kertaan
(diagnostics.txt 10.9.2026). Ennen kuin lukua yritetään nopeuttaa, on
mitattava kaksi asiaa:
  1. purkautuuko aika dekoodaukseen vai voxelointiin
  2. vapauttaako lukija GIL:n — jos vapauttaa, säikeet riittävät eikä
     tarvita prosesseja (PyInstaller + multiprocessing on oma riskinsä)

Kaytto:  _read_probe.py <e57-hakemisto> [tiedostoja]
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np


def _one(path: Path, z_lo: float, z_hi: float, voxel: float) -> int:
    from ordinate.core.geometry.streaming import load_floor_slice
    c = load_floor_slice([path], z_lo, z_hi, voxel_size=voxel, progress_cb=None)
    return len(c.points)


def main(d: str, n: int = 4) -> None:
    paths = sorted(Path(d).glob("*.e57"))[:int(n)]
    if not paths:
        print(f"ei e57-tiedostoja: {d}")
        return
    mb = sum(p.stat().st_size for p in paths) / 1e6
    print(f"{len(paths)} tiedostoa, {mb:.0f} MB")
    from ordinate.core.geometry.floor_splitter import detect_floors_from_files
    z_lo, z_hi = detect_floors_from_files(paths, sample_step=max(1, len(paths)))[0]
    print(f"kaista {z_lo/1000:.2f}–{z_hi/1000:.2f} m")

    for voxel, tag in ((20.0, "voxel 20mm"), (0.0, "taysi resa")):
        t = time.perf_counter()
        seq = [_one(p, z_lo, z_hi, voxel) for p in paths]
        t_seq = time.perf_counter() - t
        t = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(4, len(paths))) as ex:
            par = list(ex.map(lambda p: _one(p, z_lo, z_hi, voxel), paths))
        t_par = time.perf_counter() - t
        same = seq == par
        print(f"  {tag:>11}: perakkain {t_seq:6.1f} s | 4 saietta {t_par:6.1f} s "
              f"| nopeutus {t_seq / max(t_par, 1e-9):.2f}x | sama tulos: {same}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

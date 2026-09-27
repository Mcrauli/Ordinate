"""Lohkoluku vs. koko tiedoston luku: sama pistejoukko, pienempi muisti?

Ajo: .venv/Scripts/python.exe data/_e57_equiv.py <tiedosto.e57>
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ordinate.core.geometry.loader import (  # noqa: E402
    e57_band_chunks, e57_point_count, e57_z_range, load_point_cloud, read_e57_z,
)


class Peak:
    def __init__(self):
        self.p = psutil.Process()
        self.peak = 0.0
        self._run = False

    def __enter__(self):
        self._run = True
        self.base = self.p.memory_info().rss / 1e9

        def s():
            while self._run:
                self.peak = max(self.peak, self.p.memory_info().rss / 1e9)
                time.sleep(0.05)
        threading.Thread(target=s, daemon=True).start()
        return self

    def __exit__(self, *a):
        self._run = False
        time.sleep(0.1)


def main() -> None:
    path = Path(sys.argv[1])
    gb = path.stat().st_size / 1e9
    print(f"{path.name}  {gb:.2f} GB, {e57_point_count(path):,} pistettä")

    with Peak() as pk:
        cloud = load_point_cloud(path)
        full = np.asarray(cloud.points).copy()
    print(f"KOKO LUKU     {len(full):,} pistettä  huippu {pk.peak:.2f} GB")
    zmin, zmax = float(full[:, 2].min()), float(full[:, 2].max())
    del cloud

    lo = zmin + 0.35 * (zmax - zmin)
    hi = zmin + 0.65 * (zmax - zmin)
    ref = full[(full[:, 2] >= lo) & (full[:, 2] <= hi)]
    ref_sorted = np.sort(ref.view([("", ref.dtype)] * 3).ravel())
    del full

    with Peak() as pk2:
        parts = list(e57_band_chunks(path, lo, hi))
        band = np.concatenate(parts) if parts else np.zeros((0, 3))
    print(f"LOHKOLUKU     {len(band):,} pistettä  huippu {pk2.peak:.2f} GB")

    same_n = len(band) == len(ref)
    band_sorted = np.sort(band.view([("", band.dtype)] * 3).ravel())
    same = same_n and bool((band_sorted == ref_sorted).all())
    print(f"\nkaista [{lo:.0f}, {hi:.0f}] mm")
    print(f"  sama pistemäärä : {same_n} ({len(band):,} vs {len(ref):,})")
    print(f"  SAMA PISTEJOUKKO: {same}")

    zr = e57_z_range(path)
    print(f"  e57_z_range     : {zr[0]:.1f} … {zr[1]:.1f}  (koko luku {zmin:.1f} … {zmax:.1f})")
    z = read_e57_z(path)
    print(f"  read_e57_z      : {len(z):,} näytettä, {z.min():.1f} … {z.max():.1f}")


if __name__ == "__main__":
    main()

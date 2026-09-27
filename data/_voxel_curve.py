"""VOXELIKAYRA: montako pistetta jaa jaljelle milläkin voxelilla.

_auto_voxel ekstrapoloi yhdesta 20 mm referenssista olettaen etta pistemaara
skaalaa 1/voxel^2. Oletus pitaa VAIN jos pilven pisteväli on tiheampi kuin
voxeli. Tama mittaa oikean kayran, jotta tavoite (~4 M tyopistetta) voidaan
asettaa mitattuna eika mallinnettuna.

Aja:  .venv\\Scripts\\python data/_voxel_curve.py data/_retail_s.ply
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from ordinate.core.geometry.floor_splitter import detect_floors_from_files
from ordinate.core.geometry.streaming import load_floor_slice


def main() -> None:
    path = Path(sys.argv[1])
    z_lo, z_hi = detect_floors_from_files([path], sample_step=1)[0]
    cloud = load_floor_slice([path], z_lo, z_hi, voxel_size=0.0, progress_cb=None)
    n0 = len(cloud.points)
    pts = np.asarray(cloud.points)
    span = pts.max(axis=0) - pts.min(axis=0)
    print(f"{path.name}: {n0:,} pistetta, laajuus "
          f"{span[0]/1000:.0f} x {span[1]/1000:.0f} x {span[2]/1000:.1f} m")
    print(f"{'voxel mm':>9}{'pisteita':>14}{'suhde':>8}")
    for v in (8, 12, 20, 25, 30, 40, 50, 60, 80, 100):
        n = len(cloud.voxel_down_sample(float(v)).points)
        print(f"{v:>9}{n:>14,}{n/n0:>8.2f}")


if __name__ == "__main__":
    main()

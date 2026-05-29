"""Generoi realistinen synteettinen testipistepilvi (PTS-formaatti, metreissä).

Huone: 8 x 6 m, 3 m korkeus.
  - 4 seinää (kohinaisina RANSAC-tasopisteinä)
  - Lattia (z=0) ja katto (z=3m)
  - 2 suorakaidepiilaria (0.3×0.3 m)
  - 2 palkkia (0.2×0.3 m, katon alla)
  - Irtokalusteita (pöytä + tuolit) krääsäksi

Ajo: python scripts/make_test_cloud.py [--out data/raw/test_room.pts]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/raw/test_room.pts")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--density", type=int, default=50,
                        help="pistettä per m² suurimmilla pinnoilla")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    d = args.density
    noise = 0.005  # 5 mm kohina metreinä

    # Huoneen mitat (metreissä — loader skaalaa × 1000 → mm)
    W, D, H = 8.0, 6.0, 3.0

    parts: list[np.ndarray] = []

    def add(pts: np.ndarray) -> None:
        parts.append(pts + rng.normal(0, noise, pts.shape))

    def flat(x0, x1, y0, y1, z, n):
        x = rng.uniform(x0, x1, n)
        y = rng.uniform(y0, y1, n)
        return np.column_stack([x, y, np.full(n, z)])

    def vert_xz(y_fixed, x0, x1, z0, z1, n):
        x = rng.uniform(x0, x1, n)
        z = rng.uniform(z0, z1, n)
        return np.column_stack([x, np.full(n, y_fixed), z])

    def vert_yz(x_fixed, y0, y1, z0, z1, n):
        y = rng.uniform(y0, y1, n)
        z = rng.uniform(z0, z1, n)
        return np.column_stack([np.full(n, x_fixed), y, z])

    # --- Lattia ja katto ---
    n_floor = int(W * D * d)
    add(flat(0, W, 0, D, 0.0, n_floor))    # lattia
    add(flat(0, W, 0, D, H,   n_floor))    # katto

    # --- Seinät ---
    n_long = int(W * H * d)
    n_short = int(D * H * d)
    add(vert_xz(0.0, 0, W, 0, H, n_long))   # etelä
    add(vert_xz(D,   0, W, 0, H, n_long))   # pohjoinen
    add(vert_yz(0.0, 0, D, 0, H, n_short))  # länsi
    add(vert_yz(W,   0, D, 0, H, n_short))  # itä

    # --- Pilarit (0.3×0.3 m) ---
    def pillar(cx, cy, w=0.3, d_=0.3, n=400):
        x = rng.uniform(cx - w/2, cx + w/2, n)
        y = rng.uniform(cy - d_/2, cy + d_/2, n)
        z = rng.uniform(0, H, n)
        return np.column_stack([x, y, z])

    add(pillar(2.0, 1.5))
    add(pillar(6.0, 1.5))

    # --- Palkit (0.2 m leveä, 0.3 m syvä, katon alla) ---
    def beam(x0, x1, cy, z_bot, z_top, n=500):
        x = rng.uniform(x0, x1, n)
        y = rng.uniform(cy - 0.1, cy + 0.1, n)
        z = rng.uniform(z_bot, z_top, n)
        return np.column_stack([x, y, z])

    add(beam(0.5, 7.5, 1.5, H - 0.3, H, 2000))   # palkki y=1.5
    add(beam(0.5, 7.5, 4.5, H - 0.3, H, 2000))   # palkki y=4.5

    # --- Krääsä: pöytä (0.8×1.6 m, 0.75 m korkea) ---
    def furniture(cx, cy, fw, fd, fh, n=150):
        x = rng.uniform(cx - fw/2, cx + fw/2, n)
        y = rng.uniform(cy - fd/2, cy + fd/2, n)
        z = rng.uniform(0, fh, n)
        return np.column_stack([x, y, z])

    add(furniture(4.0, 3.5, 1.6, 0.8, 0.75, n=600))   # pöytä
    add(furniture(3.2, 3.5, 0.4, 0.4, 0.90, n=400))   # tuoli 1
    add(furniture(4.8, 3.5, 0.4, 0.4, 0.90, n=400))   # tuoli 2
    add(furniture(5.5, 1.0, 0.6, 0.6, 1.80, n=500))   # kaappi

    all_pts = np.vstack(parts)
    n_total = len(all_pts)
    print(f"Pisteitä yhteensä: {n_total:,}")
    print(f"Bounding box: X {all_pts[:,0].min():.2f}–{all_pts[:,0].max():.2f} m, "
          f"Y {all_pts[:,1].min():.2f}–{all_pts[:,1].max():.2f} m, "
          f"Z {all_pts[:,2].min():.2f}–{all_pts[:,2].max():.2f} m")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(f"{n_total}\n")
        for row in all_pts:
            f.write(f"{row[0]:.4f} {row[1]:.4f} {row[2]:.4f}\n")

    print(f"Tallennettu: {out.resolve()} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

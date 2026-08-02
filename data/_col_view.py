"""PILARIEHDOKKAAN KATSELU: onko se hormi/pilari vai kaappi/kaluste.

Pelkka mittaluku (324x685, aspect 2.1) ei ratkaise: asunnossa tayskorkea
suorakaide voi olla ilmanvaihtohormi (= aito rakenne) tai jaakaappi (= kaluste).
Piirtaa jokaisesta ehdokkaasta kolme kuvaa samasta kohteesta:
  1. XY-leikkaus vyotarokorkeudelta (1.0-1.8 m)  -> muoto + mika on ymparilla
  2. XY-leikkaus katon alta                      -> jatkuuko ylos asti
  3. pystyleikkaus (X-Z)                         -> ulottuuko lattiasta kattoon

Aja:  _col_view.py <pilvi.ply> <model.json> <ulos.png>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d

_WIN = 1800.0     # mm, puolikas ikkuna ehdokkaan ymparilla


def main() -> None:
    ply, model_json, out_png = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    m = json.loads(model_json.read_text(encoding="utf-8"))
    cols = m.get("columns") or []
    if not cols:
        print("ei pilariehdokkaita"); return

    pts = np.asarray(o3d.io.read_point_cloud(str(ply)).points)
    if np.ptp(pts[:, 2]) < 100:      # metreina -> mm
        pts = pts * 1000.0
    z0, z1 = np.percentile(pts[:, 2], 1), np.percentile(pts[:, 2], 99)
    print(f"{len(pts):,} pistetta, z {z0:.0f}..{z1:.0f} mm")

    n = len(cols)
    fig, axes = plt.subplots(n, 3, figsize=(15, 4.6 * n), squeeze=False)
    for i, c in enumerate(cols):
        cx, cy = float(c["location"][0]), float(c["location"][1])
        near = pts[(np.abs(pts[:, 0] - cx) < _WIN) & (np.abs(pts[:, 1] - cy) < _WIN)]
        p = c["profile"]
        ttl = f"{c['id']} {p['width']:.0f}x{p['depth']:.0f} h={c['height']:.0f} conf={c['confidence']}"

        for j, (lo, hi, name) in enumerate((
            (z0 + 1000, z0 + 1800, "vyotaro 1.0-1.8 m"),
            (z1 - 900, z1 - 300, "katon alla"),
        )):
            ax = axes[i][j]
            b = near[(near[:, 2] > lo) & (near[:, 2] < hi)]
            ax.scatter(b[:, 0], b[:, 1], s=0.6, c=b[:, 2], cmap="viridis", linewidths=0)
            ax.add_patch(plt.Rectangle((cx - p["width"] / 2, cy - p["depth"] / 2),
                                       p["width"], p["depth"], fill=False,
                                       ec="red", lw=2))
            ax.set_aspect("equal"); ax.set_title(f"{ttl}\n{name} ({len(b)} pist.)", fontsize=8)
            ax.set_xlim(cx - _WIN, cx + _WIN); ax.set_ylim(cy - _WIN, cy + _WIN)

        ax = axes[i][2]
        slab = near[np.abs(near[:, 1] - cy) < 300]
        ax.scatter(slab[:, 0], slab[:, 2], s=0.6, c="0.35", linewidths=0)
        ax.axvline(cx - p["width"] / 2, color="red", lw=1)
        ax.axvline(cx + p["width"] / 2, color="red", lw=1)
        ax.set_title(f"pystyleikkaus X-Z (|dy|<300)\nlattia {z0:.0f} katto {z1:.0f}", fontsize=8)
        ax.set_xlim(cx - _WIN, cx + _WIN)

    fig.tight_layout()
    fig.savefig(out_png, dpi=115)
    print(f"kirjoitettu {out_png}")


if __name__ == "__main__":
    main()

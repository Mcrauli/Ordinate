"""Mita malli EI kata: seinamaiset pisteet lunastettu vs lunastamatta.

Kattavuusluku kertoo paljonko jai mallintamatta, ei MITA. Tama piirtaa saman
asian: harmaa = mallin kaistassa, punainen = seinamainen pystypinta jota
yksikaan seina ei lunasta. Kolme ruutua eri kohdista, jotta yksi hyva nurkka
ei anna vaaraa kuvaa kokonaisuudesta.

Kaytto: _residual_view.py <model.json> <wallish.npz> <ulos.png> [x0 y0 koko_m]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def main(model_json: str, wallish_npz: str, out: str, *box) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    z = np.load(wallish_npz)
    q = z["q"].astype(np.float64)
    w = q[z["m"]]
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))

    xy = w[:, :2]
    claimed = np.zeros(len(w), dtype=bool)
    axes = []
    for x in m["walls"]:
        ax = x.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 800.0:
            continue
        axes.append((a, b))
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        claimed |= ((s > 0) & (s < L)
                    & (np.abs(np.abs(t) - x["thickness"] / 2.0) < 80.0))
    print(f"seinamaisia {len(w):,}  lunastettu {int(claimed.sum()):,} "
          f"({claimed.mean():.3f})")

    if box:
        boxes = [(float(box[0]) * 1000, float(box[1]) * 1000, float(box[2]) * 1000)]
    else:
        c = np.median(xy, axis=0)
        boxes = [(c[0] - 15000, c[1] - 15000, 30000),
                 (c[0] + 15000, c[1] - 15000, 30000),
                 (c[0] - 15000, c[1] + 15000, 30000)]

    fig, axs = plt.subplots(1, len(boxes), figsize=(11 * len(boxes), 10))
    axs = np.atleast_1d(axs)
    for a_, (x0, y0, s_) in zip(axs, boxes):
        sel = ((xy[:, 0] > x0) & (xy[:, 0] < x0 + s_)
               & (xy[:, 1] > y0) & (xy[:, 1] < y0 + s_))
        a_.scatter(xy[sel & claimed, 0] / 1000, xy[sel & claimed, 1] / 1000,
                   s=2.0, c="0.55", lw=0, label="lunastettu")
        a_.scatter(xy[sel & ~claimed, 0] / 1000, xy[sel & ~claimed, 1] / 1000,
                   s=2.0, c="crimson", lw=0, label="LUNASTAMATTA")
        for a, b in axes:
            a_.plot([a[0] / 1000, b[0] / 1000], [a[1] / 1000, b[1] / 1000],
                    c="tab:blue", lw=1.2, alpha=0.9)
        a_.set_xlim(x0 / 1000, (x0 + s_) / 1000)
        a_.set_ylim(y0 / 1000, (y0 + s_) / 1000)
        a_.set_aspect("equal")
        a_.set_title(f"{s_/1000:.0f} x {s_/1000:.0f} m  ({x0/1000:.0f}, {y0/1000:.0f})")
    axs[0].legend(loc="upper right", markerscale=6)
    plt.tight_layout()
    plt.savefig(out, dpi=110)
    print(f"kirjoitettu {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])

"""Puuttuva kattavuus kuvana: GT-seinäpisteet, lunastetut vs lunastamattomat.

Luku 0.792 ei kerro MIKSI. Tämä piirtää GT:n seinäpisteet vyötärökaistalta
niin että mallin lunastamat ovat harmaita ja puuttuvat punaisia, ja mallin
akselit sinisinä. Vasta tästä näkee onko kyse rinnakkaisesta seinälinjasta,
seinien päistä vai kokonaan löytymättömistä väliseinistä.

Ajo: .venv/Scripts/python.exe data/_gap_view.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_BAND = 80.0
_STRUCT_IDS = [5, 6, 8, 15]          # Wall, Drywall, Parapet, Facade Element
MODEL = Path("data/output/_rohbau_site_07_scene_07000/floor_00/model.json")
SCENE = Path("data/_rohbau/site_07/scene_07000")


def main() -> None:
    m = json.loads(MODEL.read_text(encoding="utf-8"))
    P = np.load(SCENE / "coord.npy").astype(np.float64)
    C = np.load(SCENE / "class.npy").ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    P, C = P[band], C[band]
    G = P[np.isin(C, _STRUCT_IDS)]

    claimed = np.zeros(len(G), bool)
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = G[:, :2] - a
        s, t = d @ u, d @ n
        claimed |= (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)

    fig, ax = plt.subplots(figsize=(13, 13))
    ok, miss = G[claimed][::20], G[~claimed][::20]
    ax.scatter(ok[:, 0], ok[:, 1], s=0.4, c="0.75", linewidths=0,
               rasterized=True, label=f"lunastettu ({claimed.mean():.1%})")
    ax.scatter(miss[:, 0], miss[:, 1], s=0.8, c="tab:red", linewidths=0,
               rasterized=True, label=f"PUUTTUU ({1 - claimed.mean():.1%})")
    for w in m["walls"]:
        (x0, y0), (x1, y1) = w["axis"]
        ax.plot([x0, x1], [y0, y1], color="tab:blue", lw=2.2, solid_capstyle="round")
        ax.annotate(w["id"].replace("wall_", ""), ((x0 + x1) / 2, (y0 + y1) / 2),
                    fontsize=7, color="tab:blue")
    ax.set_aspect("equal")
    ax.legend(loc="upper right", fontsize=9, markerscale=12)
    ax.set_title("Rohbau: mikä GT-seinä jää mallintamatta (punainen)", fontsize=11)
    fig.tight_layout()
    out = Path("data/_gap_view.png")
    fig.savefig(out, dpi=150)
    print(f"kuva: {out}")


if __name__ == "__main__":
    main()

"""SEINÄN KATSELU: onko liputettu seinä haamu, vai onko se vain väärässä paikassa?

`Wall.support` kertoo että pinnalla ei ole pisteitä — muttei sitä MIKÄ siellä on.
Piirtää seinästä kolme kuvaa:
  1. XY-leikkaus vyötäröltä  -> onko lähellä todellinen pinta, ja missä
  2. poikkileikkaus (perp-Z)  -> mihin etäisyyteen pisteet asettuvat mallin nähden
  3. pituusleikkaus (pituus-Z) -> onko pinta olemassa koko matkalta

Aja:  _wall_view.py <pilvi.ply> <model.json> <wall_id> <ulos.png>
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scan2bim.schemas.model import StructuralModel  # noqa: E402

_SEEK = 1500.0     # mm — kuinka kaukaa pintaa etsitään


def main() -> None:
    cloud_p, model_p, wid, out_p = sys.argv[1:5]
    model = StructuralModel.load(model_p)
    w = next(x for x in model.walls if x.id == wid)

    P = np.asarray(o3d.io.read_point_cloud(cloud_p).points)
    if np.ptp(P[:, 0]) < 500.0:
        P = P * 1000.0

    p0 = np.array(w.axis[0], float)
    p1 = np.array(w.axis[1], float)
    L = float(np.linalg.norm(p1 - p0))
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    rel = P[:, :2] - p0
    t = rel @ u
    perp = rel @ n
    z = P[:, 2]
    sel = (t > -500) & (t < L + 500) & (np.abs(perp) < _SEEK) \
        & (z > w.z_min) & (z < w.z_min + w.height)
    t, perp, z = t[sel], perp[sel], z[sel]
    if len(t) > 400_000:
        k = np.random.default_rng(0).choice(len(t), 400_000, replace=False)
        t, perp, z = t[k], perp[k], z[k]

    half = w.thickness / 2.0
    fig, ax = plt.subplots(1, 3, figsize=(19, 5.5))
    fig.suptitle(f"{wid}  L={L/1000:.1f} m  paksuus={w.thickness:.0f} mm  "
                 f"tuki={w.support}  siirtymä={w.support_offset}", fontsize=12)

    zm = (z > w.z_min + 1000) & (z < w.z_min + 1800)
    ax[0].scatter(t[zm] / 1000, perp[zm], s=0.2, c="#3366cc", alpha=0.35)
    for s, lab in ((half, "mallin pinta"), (-half, None)):
        ax[0].axhline(s, color="crimson", lw=1.4, label=lab)
    ax[0].axhline(0, color="crimson", ls=":", lw=1, label="mallin akseli")
    ax[0].set_xlabel("pituus [m]"); ax[0].set_ylabel("etäisyys akselista [mm]")
    ax[0].set_title("1) XY vyötäröltä (1.0–1.8 m)"); ax[0].legend(fontsize=8)
    ax[0].set_ylim(-_SEEK, _SEEK)

    ax[1].scatter(perp, z / 1000, s=0.2, c="#3366cc", alpha=0.35)
    ax[1].axvline(half, color="crimson", lw=1.4)
    ax[1].axvline(-half, color="crimson", lw=1.4)
    ax[1].set_xlabel("etäisyys akselista [mm]"); ax[1].set_ylabel("z [m]")
    ax[1].set_title("2) poikkileikkaus"); ax[1].set_xlim(-_SEEK, _SEEK)

    face = np.abs(np.abs(perp) - half) < 80.0
    ax[2].scatter(t[face] / 1000, z[face] / 1000, s=0.3, c="#2e8b57", alpha=0.5)
    ax[2].set_xlabel("pituus [m]"); ax[2].set_ylabel("z [m]")
    ax[2].set_title(f"3) mallin pinnalla olevat pisteet ({int(face.sum())} kpl)")
    ax[2].set_xlim(-0.5, L / 1000 + 0.5)

    hist, edges = np.histogram(perp, bins=60, range=(-_SEEK, _SEEK))
    pk = 0.5 * (edges[hist.argmax()] + edges[hist.argmax() + 1])
    print(f"{wid}: pisteitä {len(t):,} | tihein pinta {pk:+.0f} mm akselista "
          f"(mallin pinta ±{half:.0f}) | pinnalla {int(face.sum())}")

    fig.tight_layout()
    fig.savefig(out_p, dpi=110)
    print(f"-> {out_p}")


if __name__ == "__main__":
    main()

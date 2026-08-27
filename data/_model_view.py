"""Malli JA pilvi samassa kuvassa — pohjapiirros + 3D + leikkaus.

Luvut eivät kerro miltä malli näyttää. Kattavuus 0.045 ja 0.108 ovat molemmat
"huonoja", mutta vasta kuva kertoo ONKO kyse siitä että seinät ovat väärissä
paikoissa vai siitä että niitä on liian vähän — ja ne vaativat eri korjauksen.

Piirtää kolme näkymää samasta mallista:
  1. POHJA      pilven pystypinnat harmaana, mallin seinät punaisena
  2. 3D         seinät laatikkoina pilven pystypintojen päällä
  3. LEIKKAUS   yksi z-kaista sivulta, kertoo osuvatko seinät korkeussuunnassa

Käyttö: _model_view.py <model.json> <pilvi> <out.png> [otsikko]
"""
from __future__ import annotations

import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402

_VOXEL = 60.0
_KNN = 24
_VERT_NZ = 0.35
_MAX_DRAW = 120_000


def _load(path: str) -> np.ndarray:
    p = pathlib.Path(path)
    if p.suffix == ".npy":
        pts = np.load(p).astype(np.float64)
    else:
        import open3d as o3d
        pts = np.asarray(o3d.io.read_point_cloud(str(p)).points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    return pts


def _vertical(pts: np.ndarray, z_lo: float, z_hi: float) -> np.ndarray:
    import open3d as o3d
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    pc = pc.voxel_down_sample(_VOXEL)
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=_KNN))
    q = np.asarray(pc.points)
    nz = np.abs(np.asarray(pc.normals)[:, 2])
    keep = (q[:, 2] > z_lo) & (q[:, 2] < z_hi) & (nz < _VERT_NZ)
    return q[keep]


def _walls(model: dict):
    out = []
    for w in model["walls"]:
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][-1], float)[:2]
        if np.linalg.norm(b - a) < 1.0:
            continue
        out.append((a, b, float(w.get("thickness", 200.0))))
    return out


def main(model_path: str, cloud_path: str, out_png: str, title: str = "") -> None:
    model = json.loads(pathlib.Path(model_path).read_text(encoding="utf-8"))
    pts = _load(cloud_path)
    zf = min((s["elevation"] for s in model["slabs"] if s["slab_type"] == "floor"),
             default=float(pts[:, 2].min()))
    zc = max((s["elevation"] for s in model["slabs"] if s["slab_type"] == "ceiling"),
             default=float(pts[:, 2].max()))
    vert = _vertical(pts, zf + 400.0, zc - 300.0)
    walls = _walls(model)
    if len(vert) > _MAX_DRAW:
        vert = vert[np.linspace(0, len(vert) - 1, _MAX_DRAW).astype(int)]

    fig = plt.figure(figsize=(20, 7.5), facecolor="white")
    fig.suptitle(f"{title}   seiniä {len(walls)}   lattia {zf:.0f} katto {zc:.0f} mm",
                 fontsize=13)

    ax = fig.add_subplot(1, 3, 1)
    ax.scatter(vert[:, 0] / 1000, vert[:, 1] / 1000, s=0.35, c="#b0b0b0",
               linewidths=0, label="pilven pystypinnat")
    for a, b, t in walls:
        ax.plot([a[0] / 1000, b[0] / 1000], [a[1] / 1000, b[1] / 1000],
                "-", color="#d81e2c", linewidth=1.8, solid_capstyle="round")
    ax.set_aspect("equal")
    ax.set_title("POHJA — harmaa: pilvi, punainen: malli")
    ax.set_xlabel("m")

    ax3 = fig.add_subplot(1, 3, 2, projection="3d")
    step = max(len(vert) // 30_000, 1)
    v = vert[::step]
    ax3.scatter(v[:, 0] / 1000, v[:, 1] / 1000, v[:, 2] / 1000, s=0.3,
                c="#c4c4c4", linewidths=0)
    for a, b, t in walls:
        for z in (zf, zc):
            ax3.plot([a[0] / 1000, b[0] / 1000], [a[1] / 1000, b[1] / 1000],
                     [z / 1000, z / 1000], color="#d81e2c", linewidth=1.2)
        ax3.plot([a[0] / 1000, a[0] / 1000], [a[1] / 1000, a[1] / 1000],
                 [zf / 1000, zc / 1000], color="#d81e2c", linewidth=0.8)
    # Lattialaatan ääriviiva 3D:hen: käyttäjä näki katselimessa heti, että
    # seinät ja lattia eivät ole samassa paikassa — 2D-pohjakuvasta sitä ei
    # näe, koska molemmat projisoituvat samaan tasoon.
    for sl in model.get("slabs", []):
        b = sl.get("boundary") or []
        if len(b) < 3:
            continue
        q = np.asarray(b, dtype=float) / 1000.0
        q = np.vstack([q, q[:1]])
        z = sl["elevation"] / 1000.0
        ax3.plot(q[:, 0], q[:, 1], np.full(len(q), z),
                 color="#2b6cb0", linewidth=1.6,
                 label=sl["slab_type"] if sl is model["slabs"][0] else None)
    ax3.set_title("3D — seinät (punainen) ja laatat (sininen)")
    ax3.set_box_aspect((1, 1, 0.35))
    ax3.view_init(elev=38, azim=-58)
    ax3.legend(loc="upper left", fontsize=8)

    ax2 = fig.add_subplot(1, 3, 3)
    mid = 0.5 * (vert[:, 1].min() + vert[:, 1].max())
    band = np.abs(vert[:, 1] - mid) < 4000.0
    ax2.scatter(vert[band, 0] / 1000, vert[band, 2] / 1000, s=0.6, c="#b0b0b0",
                linewidths=0)
    for a, b, t in walls:
        if abs((a[1] + b[1]) / 2 - mid) < 4000.0:
            ax2.plot([a[0] / 1000, b[0] / 1000], [zf / 1000 + 0.05, zf / 1000 + 0.05],
                     color="#d81e2c", linewidth=2.5)
    ax2.axhline(zf / 1000, color="#2b6cb0", linewidth=1, label="lattia")
    ax2.axhline(zc / 1000, color="#2b6cb0", linewidth=1, linestyle="--", label="katto")
    ax2.set_title("LEIKKAUS 8 m kaista keskeltä")
    ax2.set_xlabel("m")
    ax2.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    print(f"kirjoitettu {out_png}  (seiniä {len(walls)}, pystypintapisteitä {len(vert):,})")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], a[3] if len(a) > 3 else "")

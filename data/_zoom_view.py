"""Zoomattu vertailu: pilven pystypinnat vs mallin seinat, seina kerrallaan.

Koko rakennuksen pohjakuvassa 300 seinaa on taplaryhma. Vasta 20-30 m ruudussa
nakee osuuko malliseina pilven pintaan vai ilmaan — ja sen erottaa silmalla
ilman ground truthia.

Kaytto: _zoom_view.py <model.json> <pilvi> <out.png> [x_keski y_keski koko_m]
"""
from __future__ import annotations

import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                 # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from scan2bim.core.qa.coverage import wallish_points   # noqa: E402


def main(model_path: str, cloud_path: str, out_png: str,
         cx: float | None = None, cy: float | None = None, size_m: float = 30.0) -> None:
    import open3d as o3d

    model = json.loads(pathlib.Path(model_path).read_text(encoding="utf-8"))
    pts = np.asarray(o3d.io.read_point_cloud(cloud_path).points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    zf = min((s["elevation"] for s in model["slabs"] if s["slab_type"] == "floor"),
             default=float(pts[:, 2].min()))
    zc = max((s["elevation"] for s in model["slabs"] if s["slab_type"] == "ceiling"),
             default=float(pts[:, 2].max()))
    is_wall, q = wallish_points(pts, zf + 400.0, zc - 300.0)
    surf = q[is_wall]

    if cx is None:
        cx, cy = float(np.median(surf[:, 0])), float(np.median(surf[:, 1]))
    half = size_m * 1000.0 / 2.0

    fig, axes = plt.subplots(1, 2, figsize=(20, 10), facecolor="white")
    for ax, (dx, dy, tag) in zip(axes, [(0.0, 0.0, "keskusta"),
                                        (size_m * 1000.0, 0.0, "viereinen ruutu")]):
        x0, x1 = cx + dx - half, cx + dx + half
        y0, y1 = cy + dy - half, cy + dy + half
        m = ((surf[:, 0] > x0) & (surf[:, 0] < x1)
             & (surf[:, 1] > y0) & (surf[:, 1] < y1))
        ax.scatter(surf[m, 0] / 1000, surf[m, 1] / 1000, s=4, c="#7a7a7a",
                   linewidths=0, label="pilven pystypinta")
        n_drawn = 0
        for w in model["walls"]:
            a = np.asarray(w["axis"][0], float)[:2]
            b = np.asarray(w["axis"][-1], float)[:2]
            if max(a[0], b[0]) < x0 or min(a[0], b[0]) > x1:
                continue
            if max(a[1], b[1]) < y0 or min(a[1], b[1]) > y1:
                continue
            ax.plot([a[0] / 1000, b[0] / 1000], [a[1] / 1000, b[1] / 1000],
                    "-", color="#d81e2c", linewidth=2.2, alpha=0.85)
            n_drawn += 1
        ax.set_xlim(x0 / 1000, x1 / 1000)
        ax.set_ylim(y0 / 1000, y1 / 1000)
        ax.set_aspect("equal")
        ax.set_title(f"{tag} — {size_m:.0f} × {size_m:.0f} m, {n_drawn} seinää")
        ax.grid(alpha=0.15)
    axes[0].legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_png, dpi=115, bbox_inches="tight")
    print(f"kirjoitettu {out_png}  keskipiste ({cx/1000:.0f}, {cy/1000:.0f}) m")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2],
         float(a[3]) * 1000 if len(a) > 3 else None,
         float(a[4]) * 1000 if len(a) > 4 else None,
         float(a[5]) if len(a) > 5 else 30.0)

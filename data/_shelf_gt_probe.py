"""Mita `remove_shelf_front_walls` oikeasti poistaa Rohbaussa?

Rohbau reitittyy `_looks_like_retail`-saannolla liiketilaksi (iso + korkea),
jolloin hyllysaannon retail-haara poistaa myos "koko seinan mittaiset hyllyt".
Betonirunkoisessa kohteessa sama kuvio on kuitenkin aito kipsiseina puolen
metrin paassa perimetrista. Tama tulostaa poistettujen seinien GT-luokkajakauman
— jos siella on Wall/Drywall, poisto oli vaara.

Ajo: .venv/Scripts/python.exe data/_shelf_gt_probe.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import DATA, OUTPUT  # noqa: E402

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

_BAND = 80.0
_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}
SCENE = Path(str(DATA / "_rohbau" / "site_07" / "scene_07000"))


def main() -> None:
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False,
                         semantic_filter_mode="pointnet")
    pipe = Pipeline(cfg)
    models = pipe.run_floors([SCENE / "cloud.ply"], Path(str(OUTPUT / "_shelfgt")))
    removed = list(pipe._shelf_fronts)
    print(f"\npoistettuja hyllyn etupintoja: {len(removed)}")
    if not removed:
        return

    P = np.load(SCENE / "coord.npy").astype(np.float64)
    C = np.load(SCENE / "class.npy").ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    zf = min((s.elevation for m in models for s in m.slabs if s.slab_type == "floor"),
             default=0.0)
    zc = max((s.elevation for m in models for s in m.slabs if s.slab_type == "ceiling"),
             default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, cls = P[band][:, :2], C[band]

    for w in removed:
        a = np.array(w.axis[0], float); b = np.array(w.axis[1], float)
        L = float(np.linalg.norm(b - a))
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        sel = (s > 0) & (s < L) & (np.abs(np.abs(t) - w.thickness / 2.0) < _BAND)
        cnt = collections.Counter(cls[sel].tolist())
        tot = max(int(sel.sum()), 1)
        top = "  ".join(f"{_REG.get(k, k)}={100 * v / tot:.0f}%"
                        for k, v in cnt.most_common(4))
        print(f"{w.id:14s} {L/1000:5.1f}m t={w.thickness:4.0f} n={int(sel.sum()):8,d}  {top}")


if __name__ == "__main__":
    main()

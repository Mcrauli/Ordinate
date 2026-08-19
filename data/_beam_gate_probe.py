"""Mille portille jokainen soffit-laikku kaatuu — oikealla detektorilla.

Scene_07000: GT:ssa 14 palkkia, mallissa 5 ja niista 2 osuu. Muut scenet
loytavat 8/15–8/19 samalla koodilla, joten kyse ei ole palkin muodosta vaan
siita mika tassa tilassa on erilaista. Tama ajaa detektorin OMAT funktiot ja
tulostaa laikun mitat ja ensimmaisen portin joka sen hylkaa — arvaus ei kelpaa.

Ajo: _beam_gate_probe.py <cloud.ply|coord.npy> <model.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scan2bim.core.segmentation import beam_detector as B  # noqa: E402


def _load(p: Path) -> np.ndarray:
    if p.suffix == ".npy":
        q = np.load(p).astype(np.float64)
        return q * 1000.0 if np.ptp(q[:, 0]) < 500.0 else q
    import open3d as o3d
    q = np.asarray(o3d.io.read_point_cloud(str(p)).points, dtype=np.float64)
    return q * 1000.0 if np.ptp(q[:, 0]) < 500.0 else q


def main(cloud_path: str, model_path: str) -> None:
    pts = _load(Path(cloud_path))
    m = json.loads(Path(model_path).read_text(encoding="utf-8"))
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"))
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"))
    height = zc - zf
    z_free = max(zf + 0.5 * height, zc - max(B._MAX_DEPTH, B._MAX_DEPTH_FRAC * height))
    min_depth = B._min_depth(height)
    print(f"lattia {zf:.0f}  katto {zc:.0f}  korkeus {height:.0f}")
    print(f"soffit-kaista {z_free:.0f} .. {zc - min_depth:.0f}"
          f"   (_MAX_DEPTH {B._MAX_DEPTH:.0f}, frac {B._MAX_DEPTH_FRAC * height:.0f}, "
          f"min_depth {min_depth:.0f})")

    cells = B._soffit_cells(pts, zf + 200.0, zc - 30.0, z_free, zc - min_depth)
    # Detektori pudottaa seinasolut ENNEN laikutusta; ilman tata luotain nayttaa
    # eri laikut kuin mita koodi oikeasti kasittelee.
    from scan2bim.schemas.model import StructuralModel
    walls = StructuralModel.load(model_path).walls
    if walls:
        cells = B._drop_wall_cells(cells, walls)
    print(f"seinasolujen poiston jalkeen {len(cells)}")
    print(f"soffit-soluja {len(cells)}")
    comps = list(B._patches(cells))
    print(f"laikkuja (>= {B._MIN_CELLS} solua) {len(comps)}")

    print(f"\n{'#':>3s} {'soluja':>7s} {'pituus':>7s} {'lev':>6s} {'syv':>6s} "
          f"{'alapinta':>9s} {'tayttö':>6s} {'suhde':>6s}  portti")
    rows = []
    for i, comp in enumerate(comps):
        xy = B._cell_xy(np.array(comp, dtype=np.int64))
        c = xy.mean(axis=0)
        A = xy - c
        _, V = np.linalg.eigh(A.T @ A / len(A))
        u, n = V[:, 1], V[:, 0]
        length = float(np.ptp(A @ u)) + B._CELL
        width = float(np.ptp(A @ n)) + B._CELL
        soffit = float(np.median([cells[k][0] for k in comp]))
        depth = zc - soffit
        fill = len(comp) / max((length / B._CELL) * (width / B._CELL), 1e-9)
        gate = "-"
        if length < B._MIN_LENGTH:
            gate = f"_MIN_LENGTH {B._MIN_LENGTH:.0f}"
        elif width > B._MAX_WIDTH:
            gate = f"_MAX_WIDTH {B._MAX_WIDTH:.0f}"
        elif length / width < B._MIN_ASPECT:
            gate = f"_MIN_ASPECT {B._MIN_ASPECT:.1f}"
        elif fill < B._MIN_FILL:
            gate = f"_MIN_FILL {B._MIN_FILL:.2f}"
        elif depth < min_depth:
            gate = f"_MIN_DEPTH {min_depth:.0f}"
        rows.append((len(comp), length, width, depth, soffit, fill,
                     length / max(width, 1e-9), gate))
    for i, r in enumerate(sorted(rows, key=lambda r: -r[1])):
        print(f"{i:3d} {r[0]:7d} {r[1]:7.0f} {r[2]:6.0f} {r[3]:6.0f} {r[4]:9.0f} "
              f"{r[5]:6.2f} {r[6]:6.1f}  {r[7]}")
    ok = sum(1 for r in rows if r[7] == "-")
    print(f"\nLAPI {ok}/{len(rows)}")
    from collections import Counter
    for g, n in Counter(r[7] for r in rows if r[7] != "-").most_common():
        print(f"  {g:22s} hylkaa {n}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

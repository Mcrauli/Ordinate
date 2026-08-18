"""Soffit-laikkujen mitat GT-luokan rinnalla, kaikki Rohbau-scenet.

Portit valitaan MITATUSTA valista, ei arvaamalla: tama tulostaa jokaisen
laikun pituuden, leveyden, syvyyden ja aspektin sen GT-Beam-osuuden kanssa,
seka summan siita mita mikakin portti maksaisi.

Ajo: _soffit_sweep.py [scene ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _soffit_probe import _BASE, _CELL, _MAX_DEPTH, _OFF, load_pts, patches, soffit_map  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scan2bim.core.segmentation.column_detector import _dist_to_walls  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402

_WALL_MARGIN = 250.0
_REG = {1: "Ceiling", 4: "Floor", 5: "Wall", 6: "Drywall", 9: "Beam", 10: "Column",
        11: "Staircase", 13: "Window", 17: "TGA", 0: "None"}

ROOT = Path(__file__).resolve().parents[1] / "data"


def rows_for(scene: str):
    sc = ROOT / "_rohbau" / "site_07" / scene
    mj = ROOT / "output" / f"_rohbau_site_07_{scene}" / "floor_00" / "model.json"
    m = json.loads(mj.read_text(encoding="utf-8"))
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 3000)
    pts = load_pts(str(sc / "coord.npy"))
    C = np.load(sc / "class.npy").ravel()
    z_free = max(zf + 0.5 * (zc - zf), zc - _MAX_DEPTH)
    cells, band = soffit_map(pts, zf + 200.0, zc - 30.0, z_free)
    Pb, Cb = pts[band], C[band]
    walls = StructuralModel.model_validate(m).walls
    if walls:
        keys = np.fromiter(cells.keys(), dtype=np.int64)
        ij = np.stack([keys // _BASE, keys % _BASE], 1).astype(float) - _OFF
        far = _dist_to_walls(ij * _CELL + _CELL / 2, walls) > _WALL_MARGIN
        cells = {int(k): cells[int(k)] for k, f in zip(keys, far) if f}
    out = []
    for comp in patches(cells):
        ij = np.array([divmod(k, _BASE) for k in comp], float) - _OFF
        xy = ij * _CELL + _CELL / 2
        z = np.array([cells[k][0] for k in comp])
        c = xy.mean(0)
        A = xy - c
        _, V = np.linalg.eigh(A.T @ A / len(A))
        u, n = V[:, 1], V[:, 0]
        L = float((A @ u).ptp()) + _CELL
        W = float((A @ n).ptp()) + _CELL
        zb = float(np.median(z))
        d = Pb[:, :2] - c
        box = (np.abs(d @ u) < L / 2) & (np.abs(d @ n) < W / 2)
        sel = box & (Pb[:, 2] < zb + 400)
        npts = int(sel.sum())
        beam = float((Cb[sel] == 9).mean()) if npts else 0.0
        dom = ""
        if npts:
            v, ct = np.unique(Cb[sel], return_counts=True)
            dom = _REG.get(int(v[ct.argmax()]), str(v[ct.argmax()]))
        top = float(Pb[box][:, 2].max()) if box.any() else zb
        fill = len(comp) / max((L / _CELL) * (W / _CELL), 1.0)
        out.append(dict(scene=scene, L=L, W=W, depth=zc - zb, asp=L / max(W, 1.0),
                        cells=len(comp), n=npts, beam=beam, gap=zc - top,
                        fill=fill, dom=dom))
    return out


def main() -> None:
    scenes = sys.argv[1:] or [f"scene_070{i:02d}" for i in range(5)]
    rows = []
    for s in scenes:
        r = rows_for(s)
        print(f"{s}: {len(r)} laikkua", flush=True)
        rows += r
    good = [r for r in rows if r["beam"] >= 0.5]
    bad = [r for r in rows if r["beam"] < 0.5]
    print(f"\nlaikkuja {len(rows)}  GT-palkkia (Beam>=50%) {len(good)}  muuta {len(bad)}")
    for key in ("L", "W", "depth", "asp", "cells", "gap", "fill"):
        g = np.array([r[key] for r in good], float)
        b = np.array([r[key] for r in bad], float)
        q = lambda a: (np.percentile(a, [5, 25, 50, 75, 95]) if len(a) else np.zeros(5))
        print(f"{key:6s} palkki {np.round(q(g)).astype(int)}   muu {np.round(q(b)).astype(int)}")

    print(f"\n{'portti':28s} {'palkkeja jaljella':>18s} {'muita jaljella':>15s}")
    for name, f in (
        ("kaikki", lambda r: True),
        ("aspekti >= 3", lambda r: r["asp"] >= 3),
        ("pituus >= 1200", lambda r: r["L"] >= 1200),
        ("leveys <= 3000", lambda r: r["W"] <= 3000),
        ("syvyys >= 150", lambda r: r["depth"] >= 150),
        ("asp>=3 & L>=1200", lambda r: r["asp"] >= 3 and r["L"] >= 1200),
        ("+ leveys <= 3000", lambda r: r["asp"] >= 3 and r["L"] >= 1200 and r["W"] <= 3000),
        ("+ solut >= 20", lambda r: r["asp"] >= 3 and r["L"] >= 1200 and r["W"] <= 3000 and r["cells"] >= 20),
        ("+ tayttoaste >= 0.5", lambda r: r["asp"] >= 3 and r["L"] >= 1200 and r["W"] <= 3000 and r["cells"] >= 20 and r["fill"] >= 0.5),
        ("+ kiinni katossa <=300", lambda r: r["asp"] >= 3 and r["L"] >= 1200 and r["W"] <= 3000 and r["cells"] >= 20 and r["fill"] >= 0.5 and r["gap"] <= 300),
    ):
        print(f"{name:28s} {sum(1 for r in good if f(r)):18d} {sum(1 for r in bad if f(r)):15d}")


if __name__ == "__main__":
    main()

"""Mihin porttiin jaannosseinaehdokkaat kaatuvat?

`residual_walls.py`:n omat portit viritettiin silloin kun mikaan ketjun
myohempi vaihe ei osannut tuomita huonoa ehdokasta. Nyt osaa (semanttinen
enemmistoaani, kontrasti, tasomaisuus, suunta), joten portteja voi loysata —
mutta vain sen verran kuin mittaus sanoo. Tama kertoo mika portti sitoo.

Vakiot luetaan moduulista, joten luvut vastaavat tuotantoa.

Kaytto: _residual_gate_probe.py <model.json> <pilvi.ply> [nimi]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import ordinate.core.semantics.residual_walls as RW  # noqa: E402


def main(model_json: str, cloud_path: str, name: str = "", close: str = "0") -> None:
    import open3d as o3d
    from scipy.ndimage import label as cc_label

    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points, dtype=np.float64)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    del pc
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))

    class W:
        def __init__(s, d):
            s.axis = d["axis"]
            s.thickness = d["thickness"]
            s.z_min = d["z_min"]
            s.height = d["height"]

    walls = [W(w) for w in m["walls"] if len(w.get("axis") or []) > 1]
    floor_z = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"),
                  default=float(np.percentile(pts[:, 2], 1)))
    ceiling_z = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
                    default=float(np.percentile(pts[:, 2], 99)))
    height = ceiling_z - floor_z
    z_lo = floor_z + min(RW._WAIST_LO_FRAC * height, RW._WAIST_LO_MM)
    z_hi = floor_z + RW._WAIST_HI * height
    band = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
    free = band[~RW._claimed(band, walls)]
    print(f"{name}: kaista {len(band):,}  lunastamatta {len(free):,}")
    if len(free) < 200:
        return

    origin = free[:, :2].min(axis=0)
    ij = np.floor((free[:, :2] - origin) / RW._CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    flat = ij[:, 0] * ny + ij[:, 1]
    counts = np.bincount(flat, minlength=nx * ny)
    occupied = counts[counts > 0]
    need = max(RW._SURF_FRAC * float(np.median(occupied)), 2.0)
    surf = (counts >= need).reshape(nx, ny)
    close = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    if close:
        from scipy import ndimage
        surf = ndimage.binary_closing(surf, structure=np.ones((close, close), bool))
    labels, ncomp = cc_label(surf, structure=np.ones((3, 3), dtype=int))
    print(f"  pintasoluja {int(surf.sum()):,} (kynnys {need:.0f} pistetta/solu), "
          f"komponentteja {ncomp}")

    why = Counter()
    survivors = []
    lab_flat = labels.ravel()
    for k in range(1, ncomp + 1):
        cx, cy = np.nonzero(labels == k)
        if len(cx) < RW._MIN_CELLS:
            why["solut alle _MIN_CELLS"] += 1
            continue
        xy = np.column_stack([cx, cy]).astype(np.float64) * RW._CELL + origin + RW._CELL / 2.0
        c = xy.mean(axis=0)
        A = xy - c
        _, V = np.linalg.eigh(A.T @ A / len(A))
        u, n = V[:, 1], V[:, 0]
        length = float((A @ u).ptp()) + RW._CELL
        width = float((A @ n).ptp()) + RW._CELL
        if length < RW._MIN_LEN:
            why["lyhyt (_MIN_LEN)"] += 1
            continue
        if width > RW._MAX_WIDTH:
            why["levea (_MAX_WIDTH)"] += 1
            continue
        if length / width < RW._MIN_ASPECT:
            why["aspekti (_MIN_ASPECT)"] += 1
            continue
        q = free[lab_flat[flat] == k]
        if not len(q):
            why["ei pisteita"] += 1
            continue
        if float(q[:, 2].ptp()) < min(RW._MIN_VSPAN_MM,
                                      RW._MIN_VSPAN_FRAC * (z_hi - z_lo)):
            why["pystyulottuvuus"] += 1
            continue
        survivors.append(length)
        why["LAPI"] += 1

    for kk, v in why.most_common():
        print(f"    {kk:24s} {v:5d}")
    if survivors:
        s = np.array(survivors)
        print(f"  lapi paasseet: {len(s)} kpl, yhteensa {s.sum()/1000:.0f} m, "
              f"pisin {s.max()/1000:.1f} m")


if __name__ == "__main__":
    main(*sys.argv[1:])

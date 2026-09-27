"""Missa vaiheessa apt2:n YLASEINA katoaa? Kaari jokaisen semantiikkavaiheen yli
ja raportoi onko seina baseline-linjalla (-3999.7,1603.3)-(1077.8,628.8) yha olemassa."""
from pathlib import Path
import numpy as np

A = np.array([-3999.7, 1603.3]); B = np.array([1077.8, 628.8])
U = (B - A) / np.linalg.norm(B - A); N = np.array([-U[1], U[0]])


def find(walls):
    hits = []
    for w in walls or []:
        ax = getattr(w, "axis", None)
        if not ax or len(ax) < 2:
            continue
        p0 = np.asarray(ax[0], float); p1 = np.asarray(ax[1], float)
        d = p1 - p0; L = float(np.linalg.norm(d))
        if L < 500:
            continue
        u = d / L
        if abs(float(u @ U)) < 0.94:
            continue
        lat = float(((p0 + p1) / 2 - A) @ N)
        if abs(lat) < 500:
            hits.append(f"{w.id}(L={L:.0f},lat={lat:+.0f},t={w.thickness:.0f},"
                        f"{getattr(w.source,'method','?')})")
    return hits


def wrap(mod, name, label):
    fn = getattr(mod, name)

    def inner(*a, **k):
        out = fn(*a, **k)
        walls = out if isinstance(out, list) else None
        if walls is not None and walls and hasattr(walls[0], "axis"):
            print(f"  [{label:26s}] n={len(walls):3d} ylaseina: {find(walls) or 'PUUTTUU'}",
                  flush=True)
        return out
    setattr(mod, name, inner)


import scan2bim.core.semantics.wall_semantics as WS
import scan2bim.core.semantics.orthogonal as OR
import scan2bim.core.semantics.corner_snap as CS
import scan2bim.core.semantics.perimeter as PM
import scan2bim.core.pipeline as PL

for mod, name in [
    (WS, "filter_structural_walls"), (WS, "refine_thicknesses"),
    (PL, "_recenter_wall_axes"), (PM, "add_perimeter_walls"),
    (WS, "_deduplicate"), (OR, "regularize_orthogonal"), (OR, "fine_rotate_walls"),
    (CS, "snap_corners"), (CS, "close_open_corners"),
    (WS, "merge_collinear_walls"), (WS, "remove_dangling_walls"),
    (PL, "_thickness_lock_walls"), (WS, "bridge_lintel_gaps"),
]:
    if hasattr(mod, name):
        wrap(mod, name, name)

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                     export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
out = Path(r"C:\Users\lauri\scan2bim\data\output\_trace_top")
models = Pipeline(cfg).run_floors(
    [Path(r"C:\Users\lauri\Downloads\aligned_low_apartment\apt.ply")], out)
for m in models:
    print("LOPPU walls=%d spaces=%d ylaseina=%s" % (len(m.walls), len(m.spaces), find(m.walls)))

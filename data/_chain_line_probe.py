"""Missa ketjun vaiheessa PUUTTUVA seinalinja katoaa (GT-vapaa).

Kohteet tulevat `_missing_line_probe.lines`-funktiosta: valmiin mallin
lunastamattomat seinamaiset linjat. Sama mekanismi kuin `_chain_gt_probe.py`,
mutta totuuden sijaan seurataan naita linjoja tuotantoasetuksilla.

Kaytto: _chain_line_probe.py <model.json> <wallish.npz> <out_dir> <e57/ply ...>
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "data")
import _chain_gt_probe as CG
from _missing_line_probe import lines


def main(mj, npz, out_dir, *inputs):
    import psutil
    psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
    from ordinate.core import pipeline as PL
    from ordinate.core.semantics import wall_semantics as WS, corner_snap as CS, orthogonal as OR
    from ordinate.core.semantics import perimeter as PM, residual_walls as RW, flatness_prune as FP
    from ordinate.core.semantics import direction_prune as DP, split_gaps as SG, contrast_prune as CP
    from ordinate.core.semantics import semantic_prune as SP, second_face as SF, overstretch as OS

    rows = lines(mj, npz, 1500.0)
    rng = np.random.default_rng(0)
    for i, r in enumerate(rows):
        P = r[6]
        if len(P) > 2000:
            P = P[rng.choice(len(P), 2000, replace=False)]
        CG._targets[i] = P
        print(f"kohde {i:2d}: L={r[0]:6.0f} MAD={r[2]:5.1f} @ {r[5][0]:.0f},{r[5][1]:.0f}", flush=True)

    wraps = [(m, n, n) for m, n in (
        (WS, "filter_structural_walls"), (WS, "refine_thicknesses"), (WS, "_deduplicate"),
        (WS, "merge_collinear_walls"), (WS, "bridge_lintel_gaps"), (WS, "remove_dangling_walls"),
        (WS, "remove_walls_beyond_scan_range"), (WS, "remove_shelf_front_walls"),
        (SG, "split_walls_at_gaps"), (WS, "prune_unsupported_walls"), (WS, "snap_displaced_walls"),
        (CS, "snap_corners"), (CS, "close_open_corners"), (OR, "regularize_orthogonal"),
        (OR, "fine_rotate_walls"), (OR, "refine_skew_walls"),
        (FP, "prune_flatless_walls"), (DP, "prune_offdirection_walls"),
        (CP, "prune_uncontrasted_walls"), (SP, "prune_non_wall_surfaces"),
        (OS, "trim_overstretched_walls"), (PL, "_recenter_wall_axes"), (PL, "_trim_wall_endpoints"), (PL, "_thickness_lock_walls"),
        (PL, "_snap_delivery_thickness"), (PL, "_align_faces_to_surface_median"))]
    for mod, name, label in wraps:
        CG._wrap(mod, name, label, extra=(PL,))

    cfg = PL.PipelineConfig(export_ifc=False, export_dxf=False, export_qa=False)
    PL.Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(
        [Path(p) for p in inputs], Path(out_dir))
    from ordinate.schemas.model import StructuralModel
    CG._snapshot("LOPULLINEN MALLI", StructuralModel.load(str(Path(out_dir) / "floor_00" / "model.json")).walls)

    ks = sorted(CG._targets)
    print()
    print(f"{'vaihe':30s} " + " ".join(f"{k:>5d}" for k in ks))
    prev = {k: None for k in ks}
    drops = {}
    for label, fr in CG._log:
        cells = []
        for k in ks:
            v = fr[k]; mark = " "
            if prev[k] is not None and prev[k] >= 0.30 > v:
                mark = "*"; drops.setdefault(label, []).append(k)
            cells.append(f"{v:4.2f}{mark}")
            prev[k] = v
        print(f"{label:30s} " + " ".join(cells))
    print("\nPUDOTUKSET vaiheittain (pituus m):")
    for label, ks_ in drops.items():
        print(f"  {label:30s} {sum(rows[k][0] for k in ks_)/1000:6.1f} m  kohteet {ks_}")
    never = [k for k in ks if max(fr[k] for _, fr in CG._log) < 0.30]
    print(f"  {'ei koskaan mallissa':30s} {sum(rows[k][0] for k in never)/1000:6.1f} m  kohteet {never}")


if __name__ == "__main__":
    main(*sys.argv[1:])

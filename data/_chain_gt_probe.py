"""Mika KETJUN vaihe pudottaa GT-seinan? Per-instanssi, ei per-luku.

`_normals_stage_probe.py` osoitti etta normals-detektori LOYTAA scene_07002:n
viisi "kukaan ei loyda" -seinaa: 57-90 % niiden pisteista paatyy valmiiseen
seinasegmenttiin. Lopullisessa mallissa niita ei ole. Havio on siis
semantics-ketjussa, ja tama kertoo minka kutsun kohdalla se tapahtuu.

`_chain_probe.py` mittaa saman ketjun pituutena ja lukumaarana; tama mittaa
sen GT-instansseina, koska seinamaaran sailyminen ei kerro etta juuri OIKEA
seina sailyi.

Kaytto: _chain_gt_probe.py <scene_dir> <out_dir> [inst,inst,...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

FACE = {5, 6, 8, 15}
MIN_PTS = 2000
MIN_FRAC = 0.30
MAX_SAMPLE = 4000

_targets: dict[int, np.ndarray] = {}
_log: list[tuple[str, dict[int, float]]] = []


def _frac(P: np.ndarray, walls) -> float:
    hit = np.zeros(len(P), bool)
    for w in walls:
        ax = getattr(w, "axis", None) or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = P[:, :2] - a
        half = 0.5 * float(getattr(w, "thickness", None) or 200.0) + 150.0
        t = d @ u
        hit |= (t >= -150.0) & (t <= L + 150.0) & (np.abs(d @ n) <= half)
    return float(hit.mean())


def _snapshot(label: str, walls) -> None:
    _log.append((label, {k: _frac(P, walls) for k, P in _targets.items()}))


def _walls_of(x):
    if isinstance(x, list):
        return x if all(hasattr(w, "axis") for w in x) else None
    w = getattr(x, "walls", None)
    return w if isinstance(w, list) else None


def _wrap(mod, name: str, label: str, extra=()) -> None:
    fn = getattr(mod, name, None)
    if fn is None:
        return

    def inner(*a, **kw):
        out = fn(*a, **kw)
        after = _walls_of(out)
        if after is None and a:
            after = _walls_of(a[0])
        if after is not None:
            _snapshot(label, after)
        return out

    setattr(mod, name, inner)
    for m in extra:
        if getattr(m, name, None) is fn:
            setattr(m, name, inner)


def main(scene_dir: str, out_dir: str, insts: str = "") -> None:
    from ordinate.core import pipeline as PL
    from ordinate.core.semantics import wall_semantics as WS
    from ordinate.core.semantics import corner_snap as CS
    from ordinate.core.semantics import orthogonal as OR
    from ordinate.core.semantics import perimeter as PM
    from ordinate.core.semantics import residual_walls as RW
    from ordinate.core.semantics import flatness_prune as FP
    from ordinate.core.semantics import direction_prune as DP
    from ordinate.core.semantics import split_gaps as SG
    from ordinate.core.segmentation import wall_normals as WN

    scene = Path(scene_dir)
    G = np.load(scene / "coord.npy").astype(np.float64)
    if float(np.ptp(G[:, 0])) < 500.0:
        G = G * 1000.0
    C = np.load(scene / "class.npy")
    I = np.load(scene / "instance.npy")
    want = {int(x) for x in insts.split(",")} if insts else None
    rng = np.random.default_rng(0)
    for k in np.unique(I):
        m = I == k
        if m.sum() < MIN_PTS or not np.isin(C[m], list(FACE)).any():
            continue
        if want is not None and int(k) not in want:
            continue
        P = G[m]
        if len(P) > MAX_SAMPLE:
            P = P[rng.choice(len(P), MAX_SAMPLE, replace=False)]
        _targets[int(k)] = P
    print(f"{scene.name}: {len(_targets)} instanssia seurannassa", flush=True)

    det = WN.NormalsWallDetector.detect

    def det_wrapped(self, cloud):
        model = det(self, cloud)
        _snapshot("detektori", model.walls)
        return model

    WN.NormalsWallDetector.detect = det_wrapped

    for mod, name, label in (
        (WS, "filter_structural_walls", "filter_structural"),
        (WS, "refine_thicknesses", "refine_thickness"),
        (WS, "_deduplicate", "dedup"),
        (WS, "merge_collinear_walls", "merge_collinear"),
        (WS, "bridge_lintel_gaps", "bridge_lintel"),
        (WS, "remove_dangling_walls", "remove_dangling"),
        (WS, "remove_walls_beyond_scan_range", "beyond_range"),
        (WS, "remove_shelf_front_walls", "shelf_front"),
        (SG, "split_walls_at_gaps", "split_gaps"),
        (WS, "prune_unsupported_walls", "prune_unsupported"),
        (WS, "snap_displaced_walls", "snap_displaced"),
        (CS, "snap_corners", "snap_corners"),
        (CS, "close_open_corners", "close_corners"),
        (OR, "regularize_orthogonal", "regularize"),
        (OR, "fine_rotate_walls", "fine_rotate"),
        (OR, "refine_skew_walls", "refine_skew"),
        (PM, "add_perimeter_walls", "perimeter"),
        (RW, "find_residual_walls", "residual"),
        (FP, "prune_flatless_walls", "flatness_prune"),
        (DP, "prune_offdirection_walls", "direction_prune"),
        (PL, "_recenter_wall_axes", "surface_lock"),
        (PL, "_trim_wall_endpoints", "trim_ends"),
        (PL, "_thickness_lock_walls", "thickness_lock"),
        (PL, "_snap_delivery_thickness", "delivery_thickness"),
        (PL, "_align_faces_to_surface_median", "align_faces"),
    ):
        _wrap(mod, name, label, extra=(PL,))

    cfg = PL.PipelineConfig(detector="normals", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    PL.Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(
        [scene / "cloud.ply"], Path(out_dir))

    ks = sorted(_targets)
    print()
    print(f"{'vaihe':22s} " + " ".join(f"{k:>7d}" for k in ks))
    prev = {k: None for k in ks}
    for label, fr in _log:
        cells = []
        for k in ks:
            v = fr[k]
            mark = " "
            if prev[k] is not None and prev[k] >= MIN_FRAC > v:
                mark = "*"
            cells.append(f"{v:6.2f}{mark}")
            prev[k] = v
        print(f"{label:22s} " + " ".join(cells))
    print()
    print("* = instanssi putosi taman vaiheen kohdalla alle kynnyksen "
          f"{MIN_FRAC}")


if __name__ == "__main__":
    main(*sys.argv[1:])

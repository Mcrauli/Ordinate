"""Mika ketjun vaihe kasvattaa seinat? Pituus ja lukumaara vaiheittain.

Kellarissa normals-detektori tuottaa 302 seinaa / 1056 m joista nelja on yli
8 m. Lopullisessa mallissa samasta lahteesta on 333 seinaa / 1753 m joista 58
on yli 8 m. Kasvu tapahtuu siis semantics-ketjussa, ei detektiossa — tama
kertoo missa.

Kaytto: _chain_probe.py <pilvi.ply> <out_dir> [max_pts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_log: list[tuple[str, int, float]] = []


def _stat(walls):
    tot = 0.0
    for w in walls:
        ax = getattr(w, "axis", None) or []
        if len(ax) > 1:
            tot += float(np.linalg.norm(np.asarray(ax[-1], float) - np.asarray(ax[0], float)))
    return len(walls), tot / 1000.0


def _wrap(mod, name, label):
    fn = getattr(mod, name)

    def inner(*a, **kw):
        before = _stat(a[0]) if a and isinstance(a[0], list) else (0, 0.0)
        out = fn(*a, **kw)
        after = _stat(out) if isinstance(out, list) else before
        _log.append((label, after[0] - before[0], after[1] - before[1]))
        return out

    setattr(mod, name, inner)


def main(cloud: str, out_dir: str, max_pts: str = "4000000") -> None:
    import open3d as o3d
    from ordinate.core import pipeline as PL
    from ordinate.core.semantics import wall_semantics as WS
    from ordinate.core.semantics import corner_snap as CS
    from ordinate.core.semantics import perimeter as PM

    src = Path(cloud)
    lim = int(max_pts)
    pc = o3d.io.read_point_cloud(str(src))
    pts = np.asarray(pc.points)
    if len(pts) > lim:
        pts = np.ascontiguousarray(pts[:: -(-len(pts) // lim)])
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(pts)
        src = Path(out_dir) / "_dec.ply"
        src.parent.mkdir(parents=True, exist_ok=True)
        o3d.io.write_point_cloud(str(src), pc)
    print(f"pisteita {len(pts):,}  -> {src}", flush=True)
    del pc, pts

    for mod, name, label in (
        (WS, "filter_structural_walls", "filter_structural"),
        (WS, "refine_thicknesses", "refine_thickness"),
        (WS, "merge_collinear_walls", "merge_collinear"),
        (WS, "_deduplicate", "dedup"),
        (CS, "snap_corners", "snap_corners"),
        (CS, "close_open_corners", "close_corners"),
        (PL, "_recenter_wall_axes", "surface_lock"),
        (PL, "_trim_wall_endpoints", "trim_ends"),
    ):
        _wrap(mod, name, label)

    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    PL.Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors([src], Path(out_dir))

    agg: dict[str, list[float]] = {}
    for label, dn, dl in _log:
        a = agg.setdefault(label, [0, 0.0, 0])
        a[0] += dn
        a[1] += dl
        a[2] += 1
    print()
    print(f"{'vaihe':20s} {'kutsuja':>8s} {'d-seinia':>9s} {'d-pituus m':>11s}")
    for label, (dn, dl, n) in sorted(agg.items(), key=lambda x: -abs(x[1][1])):
        print(f"{label:20s} {n:8d} {dn:9d} {dl:11.0f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

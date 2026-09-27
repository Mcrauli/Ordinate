"""Paksuuden pintapari: vahvin piikki vs. vahvin VASTAKKAISELTA puolelta.

`_thickness_lock_wall` valitsee seinan toiseksi pinnaksi toiseksi vahvimman
piikin 50-400 mm etaisyydelta RIIPPUMATTA siita kummalla puolella akselia se
on. Puhtaassa datassa ne ovat seinan kaksi pintaa; putkikellarissa lahin putki
voittaa aidon vastapinnan. Mitattu kellarilla (piikkipari harvennetusta
pilvesta): malli 66 mm, pinnat 225 mm etaisyydella, mediaanivirhe +109 mm ja
30/57 seinaa yli 100 mm alakanttiin. Sama koetin antaa asunnolle 150 mm
(malli 154) ja Rohbaulle 112 mm (malli 120), eli se ei valehtele siella missa
malli on oikeassa.

Tama ajaa putken kahdesti samalle pilvelle ja tulostaa paksuusjakauman.

Kaytto: _thick_ablation.py <pilvi.ply> <out_dir> [max_pts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _opposite_side_pick(hist, centers, pks, dom, lo, hi):
    """Vahvin piikki dominantin VASTAKKAISELTA puolelta akselia."""
    d0 = float(centers[dom])
    cands = [int(p) for p in pks if int(p) != dom
             and np.sign(float(centers[p])) != np.sign(d0)
             and lo <= abs(float(centers[p]) - d0) <= hi]
    if not cands:
        return None
    return max(cands, key=lambda p: hist[p])


def main(cloud: str, out_dir: str, max_pts: str = "4000000") -> None:
    import open3d as o3d
    from ordinate.core import pipeline as PL

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
    del pc
    print(f"pisteita {len(pts):,}", flush=True)

    from ordinate.core.qa.coverage import wall_coverage
    orig = PL._thickness_lock_wall

    def patched(wall, p, ceiling_xy=None, inward=None, index=None):
        PL._PAIR_OPPOSITE = True
        try:
            return orig(wall, p, ceiling_xy, inward, index=index)
        finally:
            PL._PAIR_OPPOSITE = False

    for name in ("nykyinen", "vastakkainen"):
        PL._PAIR_OPPOSITE = (name == "vastakkainen")
        cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                                export_dxf=False, export_qa=False,
                                semantic_filter_mode="pointnet")
        m = PL.Pipeline(cfg, progress=lambda s: None).run_floors(
            [src], Path(out_dir) / name)[0]
        th = np.array([w.thickness for w in m.walls])
        mt = np.array([w.measured_thickness for w in m.walls
                       if w.measured_thickness is not None])
        fz = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
        cz = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"),
                 default=fz + 2700.0)
        cov = wall_coverage(pts, m.walls, fz, cz)
        print(f"{name:13s} seinia {len(m.walls):4d}  paksuus med {np.median(th):5.0f} mm  "
              f"mitattu med {np.median(mt) if len(mt) else -1:5.0f} mm  "
              f"kattavuus {cov:.3f}", flush=True)
    PL._PAIR_OPPOSITE = False


if __name__ == "__main__":
    main(*sys.argv[1:])

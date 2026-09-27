"""Ablaatio: paljonko nurkkajatko kasvattaa mallia, ja maksaako se mitaan.

`snap_corners` ajetaan ketjussa kahdeksan kertaa ja jokainen kutsu saa jatkaa
seinan pään 1300 mm risteykseen. Raja on siis per KUTSU eika per seina: 3 m
detektiopatka voi kasvaa yli 20 m ilman etta yksikaan askel rikkoo saantoa.
Mitattu kellarilla (`_chain_probe.py`): snap_corners lisaa +2009 m, kaikki muu
yhteensa −270 m.

Kaytto: _snap_ablation.py <pilvi.ply> <out_dir> <ext_mm> [max_pts]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(cloud: str, out_dir: str, ext_mm: str, max_pts: str = "4000000") -> None:
    import open3d as o3d
    from ordinate.core import pipeline as PL
    from ordinate.core.semantics import corner_snap as CS
    from ordinate.core.qa.coverage import wall_coverage

    ext = float(ext_mm)
    CS._MAX_EXTEND = ext
    CS._RES_EXTEND = ext

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

    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    models = PL.Pipeline(cfg, progress=lambda m: print(m, flush=True)).run_floors(
        [src], Path(out_dir))
    m = models[0]
    length = sum(float(np.linalg.norm(np.asarray(w.axis[-1], float)
                                      - np.asarray(w.axis[0], float)))
                 for w in m.walls if len(w.axis) > 1) / 1000.0
    fz = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
    cz = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"),
             default=fz + 2700.0)
    cov = wall_coverage(pts, m.walls, fz, cz)
    print(f"\nJATKO {ext:.0f} mm: seinia {len(m.walls)}  pituus {length:.0f} m  "
          f"kattavuus {cov:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

"""Mita malli olisi ILMAN nurkkakoneistoa?

Ketju on rakennettu puhtaalle huoneelle: `regularize_orthogonal` pakottaa
seinat perhesuuntiin, `snap_corners` ja `close_open_corners` venyttavat paita
risteyksiin, `merge_collinear_walls` sulauttaa patkia. Matalassa sokkeloisessa
kellarissa jokainen naista oletuksista pettaa — mitattu: ketju kasvattaa mallia
+2009 m ja 58 % lopputuloksen pituudesta osoittaa suuntaan jota pilvi ei tue.

Tama ajaa saman putken niin etta neljä vaihetta ovat identiteetteja, ja
tulostaa kattavuuden ja tarkkuuden. Jos malli PARANEE ilman niita, ketju on
vaara tyokalu tahan tilaan eika sita pida korjata portilla.

Kaytto: _chain_ablation.py <pilvi.ply> <out_dir> [max_pts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def main(cloud: str, out_dir: str, max_pts: str = "0", which: str = "all") -> None:
    import open3d as o3d
    from ordinate.core import pipeline as PL
    from ordinate.core.semantics import corner_snap as CS
    from ordinate.core.semantics import orthogonal as OR
    from ordinate.core.semantics import wall_semantics as WS
    from ordinate.core.qa.coverage import wall_coverage

    src = Path(cloud)
    pc = o3d.io.read_point_cloud(str(src))
    pts = np.asarray(pc.points)
    lim = int(max_pts)
    if lim and len(pts) > lim:
        pts = np.ascontiguousarray(pts[:: -(-len(pts) // lim)])
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(pts)
        src = Path(out_dir) / "_dec.ply"
        src.parent.mkdir(parents=True, exist_ok=True)
        o3d.io.write_point_cloud(str(src), pc)
    del pc

    which = sys.argv[4] if len(sys.argv) > 4 else "all"
    if which in ("all", "snap"):
        CS.snap_corners = lambda walls, preserve_lines=False: walls
        PL.snap_corners = CS.snap_corners
    if which in ("all", "close"):
        CS.close_open_corners = lambda walls: walls
        PL.close_open_corners = CS.close_open_corners
    if which in ("all", "regular"):
        OR.regularize_orthogonal = lambda walls, drop_skew=False, **kw: walls
    if which in ("all", "merge"):
        WS.merge_collinear_walls = lambda walls, *a, **kw: walls
    print(f"ABLAATIO: {which}", flush=True)

    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="auto")
    m = PL.Pipeline(cfg, progress=lambda s: print(s, flush=True)).run_floors(
        [src], Path(out_dir))[0]
    fz = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
    cz = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"),
             default=fz + 2700.0)
    cov = wall_coverage(pts, m.walls, fz, cz)
    length = sum(float(np.linalg.norm(np.asarray(w.axis[-1], float)
                                      - np.asarray(w.axis[0], float)))
                 for w in m.walls if len(w.axis) > 1) / 1000.0
    print(f"\nILMAN NURKKAKONEISTOA: {len(m.walls)} seinaa, {length:.0f} m, "
          f"kattavuus {cov:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

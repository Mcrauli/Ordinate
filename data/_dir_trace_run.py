"""Aja putki ja tulosta direction_prunen seinakohtaiset arvot."""
import sys
from pathlib import Path

import numpy as np

if __name__ == "__main__":
    from ordinate.core.semantics import direction_prune as DP
    from ordinate.core import pipeline as PL

    orig = DP.prune_offdirection_walls

    def traced(model, cloud, floor_z, ceiling_z, wallish=None):
        from ordinate.core.semantics.contrast_prune import wallish_of
        got = wallish_of(cloud, floor_z, ceiling_z) if wallish is None else wallish
        mask, q = got
        W = q[mask]
        hist, cen = DP._histogram(W)
        top = np.argsort(hist)[::-1][:6]
        print(f"DIR fz={floor_z:.0f} cz={ceiling_z:.0f} wallish={len(W)} huiput",
              [(round(float(cen[i])), round(float(hist[i] / hist.max()), 2)) for i in top])
        for w in model.walls:
            a = np.asarray(w.axis[0], float); b = np.asarray(w.axis[-1], float)
            deg = (np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])) + 90) % 180
            print(f"DIR  {w.id:14s} L={np.linalg.norm(b-a):6.0f} normaali {deg:5.1f} tuki {DP.direction_support(w, hist, cen, float(hist.max()))}")
        return orig(model, cloud, floor_z, ceiling_z, wallish=wallish)

    DP.prune_offdirection_walls = traced
    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
    PL.Pipeline(cfg, progress=lambda s: None).run_floors([Path(sys.argv[1])], Path(sys.argv[2]))

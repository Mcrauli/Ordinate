"""Aja pelkka pilaridetektio valmiiseen malliin (vrt. `_beam_run.py`)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _soffit_probe import load_pts  # noqa: E402

from ordinate.core.segmentation.column_detector import detect_columns  # noqa: E402
from ordinate.schemas.model import StructuralModel  # noqa: E402


def main(cloud_path: str, model_json: str) -> None:
    m = StructuralModel.load(model_json)
    zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
    zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=zf + 3000.0)
    pts = load_pts(cloud_path)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    m.columns = detect_columns(pcd, m.walls, zf, zc)
    out = str(Path(model_json).with_suffix(".cols.json"))
    m.save(out)
    print(f"{Path(model_json).parent.parent.name}: {len(m.columns)} pilaria "
          f"(lattia {zf:.0f} katto {zc:.0f})")
    for c in m.columns[:8]:
        print(f"  {c.id} {c.profile.width:5.0f}x{c.profile.depth:5.0f} "
              f"kork {c.height:6.0f} alaosa {c.base_z:7.0f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

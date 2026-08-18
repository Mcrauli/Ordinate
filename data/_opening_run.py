"""Aja pelkka aukkodetektio valmiiseen malliin (vrt. `_beam_run.py`)."""
from __future__ import annotations

import sys
from pathlib import Path

import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _soffit_probe import load_pts  # noqa: E402

from scan2bim.core.segmentation.opening_detector import detect_openings  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402


def main(cloud_path: str, model_json: str) -> None:
    m = StructuralModel.load(model_json)
    zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
    pts = load_pts(cloud_path)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    m.openings = detect_openings(m.walls, pcd, zf)
    out = str(Path(model_json).with_suffix(".ops.json"))
    m.save(out)
    d = sum(1 for o in m.openings if o.opening_type == "door")
    print(f"{Path(model_json).parent.parent.name}: {len(m.openings)} aukkoa "
          f"(ovia {d}, ikkunoita {len(m.openings) - d})")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

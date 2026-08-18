"""Aja pelkka palkkidetektio olemassa olevaan malliin ja mittaa GT:ta vasten.

Koko putken ajaminen kestaa minuutteja per scene, mutta palkkidetektio tarvitsee
vain pilven, seinat ja laattakorkeudet. Tama lukee valmiin `model.json`:n,
korvaa sen palkit ja kirjoittaa rinnalle `model.beams.json`:n jota
`_beam_qa.py` lukee.

Ajo: _beam_run.py <cloud.ply|coord.npy> <model.json>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _soffit_probe import load_pts  # noqa: E402

from scan2bim.core.segmentation.beam_detector import detect_beams  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402


def main(cloud_path: str, model_json: str) -> str:
    m = StructuralModel.load(model_json)
    zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
    zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=None)
    has_ceiling = zc is not None
    if zc is None:
        zc = zf + 3000.0
    pts = load_pts(cloud_path)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    m.beams = detect_beams(pcd, m.walls, zf, zc, has_ceiling=has_ceiling)
    out = str(Path(model_json).with_suffix(".beams.json"))
    m.save(out)
    print(f"{Path(model_json).parent.parent.name}: {len(m.beams)} palkkia "
          f"(lattia {zf:.0f} katto {zc:.0f} has_ceiling={has_ceiling})")
    for b in m.beams[:10]:
        a = np.array(b.axis[0][:2]); q = np.array(b.axis[1][:2])
        print(f"  {b.id} L={np.linalg.norm(q - a):6.0f} lev={b.profile.width:6.0f} "
              f"syv={b.profile.height:6.0f} z={b.axis[0][2]:7.0f}")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

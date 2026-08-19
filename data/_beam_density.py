"""Antaako palkkidetektori saman tuloksen samasta tilasta eri tiheydella.

Tama on yleistyvyyden kovin testi: sama rakennus, sama geometria, vain
pisteita eri maara. Jos tulos muuttuu, mittari on sidottu skannin tiheyteen
eika rakennukseen — eika sita saa luvata toimivaksi tuntemattomalla skannilla.

Mitattu lahtotilanne (voxel mm -> instanssikattavuus, scene_07000, koko putki):
0 -> 0.143, 10 -> 0.143, 20 -> 0.000, 40 -> 0.643, 80 -> 0.429.

Ajaa VAIN palkkidetektorin, ei putkea: ero on puhtaasti detektorin.

Ajo: _beam_density.py [scene] [voxel_mm ...]
"""
from __future__ import annotations

import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _beam_qa  # noqa: E402
from _paths import DATA, OUTPUT  # noqa: E402

from scan2bim.core.segmentation.beam_detector import detect_beams  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402

_SITE = "site_07"


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def main() -> None:
    scene = sys.argv[1] if len(sys.argv) > 1 else "scene_07000"
    voxels = [float(v) for v in sys.argv[2:]] or [0.0, 10.0, 20.0, 40.0, 80.0]
    sd = Path(str(DATA / "_rohbau" / _SITE / scene))
    mj = Path(str(OUTPUT / f"_rohbau_{_SITE}_{scene}" / "floor_00" / "model.json"))
    base = o3d.io.read_point_cloud(str(sd / "cloud.ply"))
    m = StructuralModel.load(str(mj))
    zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
    zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=None)
    has_ceiling = zc is not None
    if zc is None:
        zc = zf + 3000.0

    rows = []
    for v in voxels:
        pc = base if v <= 0.0 else base.voxel_down_sample(v / 1000.0)
        pts = np.asarray(pc.points, dtype=np.float64)
        if np.ptp(pts[:, 0]) < 500.0:
            pts = pts * 1000.0
        q = o3d.geometry.PointCloud()
        q.points = o3d.utility.Vector3dVector(pts)
        m.beams = detect_beams(q, m.walls, zf, zc, has_ceiling=has_ceiling)
        out = str(mj.with_suffix(".dens.json"))
        m.save(out)
        buf = io.StringIO()
        with redirect_stdout(buf):
            _beam_qa.main(out, str(sd / "coord.npy"), str(sd / "class.npy"))
        t = buf.getvalue()
        rows.append((v, len(pts), len(m.beams),
                     _num(r"INSTANSSIKATTAVUUS (\d+/\d+)", t),
                     _num(r"INSTANSSIKATTAVUUS \d+/\d+ = ([\d.]+)", t),
                     _num(r"TARKKUUS.*?([\d.]+)", t)))
        print(f"  voxel {v:3.0f} -> {rows[-1][3]} tark={rows[-1][5]}", flush=True)

    print("")
    print(f"{'voxel':>6s} {'pisteita':>12s} {'palkkeja':>8s} {'inst':>8s} "
          f"{'kattavuus':>9s} {'tarkkuus':>8s}")
    for r in rows:
        print(f"{r[0]:6.0f} {r[1]:12,d} {r[2]:8d} {r[3]:>8s} {r[4]:>9s} {r[5]:>8s}")
    vals = [float(r[4]) for r in rows if r[4] not in ("-", "")]
    if vals:
        print(f"\nHAJONTA {min(vals):.3f} .. {max(vals):.3f}  "
              f"(vaihteluvali {max(vals) - min(vals):.3f}) — tavoite on 0.")


if __name__ == "__main__":
    main()

"""Onko aukon leveyskatto sidottu rakennuksen kokoon?

Scene_07004: ehdokkaat 3719 mm ja 5066 mm kaatuvat `_MAX_W`:hen (3000). Kymmenen
metrin hallissa nostoovi on 4-5 m levea, joten kiintea katto on sama virhe kuin
palkin kiintea `_MIN_DEPTH`. Suhteellinen katto `_MAX_FRACTION` (50 % seinasta)
on jo olemassa; kysymys on kumpi sitoo ja mita se maksaa.

Ajaa VAIN aukkodetektorin ja mittaa GT:ta vasten. Jos katon nosto yhdistaa
useita aukkoja yhdeksi, tarkkuus romahtaa — ja silloin sita ei nosteta.

Ajo: _opening_width_sweep.py [max_w ...]
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

import _opening_qa  # noqa: E402
from _paths import DATA, OUTPUT  # noqa: E402

from ordinate.core.segmentation import opening_detector as O  # noqa: E402
from ordinate.schemas.model import StructuralModel  # noqa: E402

_SITE = "site_07"


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def main() -> None:
    widths = [float(v) for v in sys.argv[1:]] or [3000.0, 4000.0, 5000.0, 6000.0]
    site = Path(str(DATA / "_rohbau" / _SITE))
    scenes = sorted(p.name for p in site.iterdir() if p.is_dir())
    orig = O._MAX_W
    rows = []
    for sc in scenes:
        mj = Path(str(OUTPUT / f"_rohbau_{_SITE}_{sc}" / "floor_00" / "model.json"))
        if not mj.exists():
            continue
        pts = np.asarray(o3d.io.read_point_cloud(
            str(site / sc / "cloud.ply")).points, dtype=np.float64)
        if np.ptp(pts[:, 0]) < 500.0:
            pts = pts * 1000.0
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        m = StructuralModel.load(str(mj))
        zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
        for mw in widths:
            O._MAX_W = mw
            m.openings = O.detect_openings(m.walls, pcd, zf)
            out = str(mj.with_suffix(".ow.json"))
            m.save(out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                _opening_qa.main(out, str(site / sc / "coord.npy"),
                                 str(site / sc / "class.npy"))
            t = buf.getvalue()
            rows.append((sc, mw, len(m.openings),
                         _num(r"ISANTASEINA MALLISSA (\d+/\d+)", t),
                         _num(r"ISANTASEINA MALLISSA \d+/\d+ = ([\d.]+)", t),
                         _num(r"mallin aukoista GT-aukolla: \d+/\d+ = ([\d.]+)", t)))
            print(f"  {sc} max_w={mw:5.0f} aukkoja={len(m.openings):3d} "
                  f"{rows[-1][3]} tark={rows[-1][5]}", flush=True)
    O._MAX_W = orig

    print("")
    print(f"{'scene':14s} {'max_w':>6s} {'aukkoja':>7s} {'isanta':>8s} "
          f"{'kattavuus':>9s} {'tarkkuus':>8s}")
    for r in rows:
        print(f"{r[0]:14s} {r[1]:6.0f} {r[2]:7d} {r[3]:>8s} {r[4]:>9s} {r[5]:>8s}")
    for mw in widths:
        sel = [r for r in rows if r[1] == mw]
        f = sum(int(r[3].split("/")[0]) for r in sel if "/" in r[3])
        n = sum(int(r[3].split("/")[1]) for r in sel if "/" in r[3])
        pr = [float(r[5]) for r in sel if r[5] not in ("-", "")]
        print(f"max_w {mw:5.0f}: yhteensa {f}/{n} = {f / max(n, 1):.3f}   "
              f"tarkkuus ka {np.mean(pr) if pr else float('nan'):.3f}")


if __name__ == "__main__":
    main()

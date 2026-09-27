"""Onko matala kattoripa palkki? Suhteellisen syvyysrajan mittaus.

Scene_07000: malli antaa 24 palkkia kun GT:ssa on 14. Ylimaaraiset ovat
2.2-13.5 m pitkia, 460-1700 mm syvia ja niiden alapinta on 7100-7740 eli
selvasti YLEMPANA kuin yhdenkaan GT-palkin (5176-6378). Kymmenen metrin
hallissa 460 mm alaslasku ei ole palkki vaan kattoripa tai kanava — mutta 2.7 m
asunnossa 200 mm alaslasku on. Absoluuttinen `_MIN_DEPTH` ei voi olla oikein
molemmissa.

Tama ajaa VAIN detektorin usealla suhteellisella syvyysrajalla ja mittaa
kattavuuden ja tarkkuuden. Jos raja poistaa yhdenkin GT-palkin, se on liian
tiukka riippumatta siita mita se tekee tarkkuudelle.

Ajo: _beam_depth_sweep.py [frac ...]
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
import _beam_synth_qa  # noqa: E402
from _paths import DATA, OUTPUT  # noqa: E402

from ordinate.core.segmentation import beam_detector as B  # noqa: E402
from ordinate.schemas.model import StructuralModel  # noqa: E402

_SITE = "site_07"


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def _cloud(path: Path):
    pts = np.asarray(o3d.io.read_point_cloud(str(path)).points, dtype=np.float64)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    return pc


def main() -> None:
    fracs = [float(v) for v in sys.argv[1:]] or [0.0, 0.03, 0.05, 0.08]
    site = Path(str(DATA / "_rohbau" / _SITE))
    cases = [(sc, site / sc / "cloud.ply",
              Path(str(OUTPUT / f"_rohbau_{_SITE}_{sc}" / "floor_00" / "model.json")),
              site / sc)
             for sc in sorted(p.name for p in site.iterdir() if p.is_dir())]
    cases += [("retail_s", Path(str(DATA / "_retail_s.ply")),
               Path(str(OUTPUT / "_2nd_retail_s" / "model.json")),
               Path(str(DATA / "_retail_s.ply.gt.json")))]

    orig = B._MIN_DEPTH
    rows = []
    for tag, cloud_p, mj, gt in cases:
        if not (cloud_p.exists() and mj.exists()):
            continue
        pcd = _cloud(cloud_p)
        m = StructuralModel.load(str(mj))
        zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
        zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=None)
        has_ceiling = zc is not None
        if zc is None:
            zc = zf + 3000.0
        for fr in fracs:
            B._MIN_DEPTH = max(orig, fr * (zc - zf))
            m.beams = B.detect_beams(pcd, m.walls, zf, zc, has_ceiling=has_ceiling)
            out = str(mj.with_suffix(".depth.json"))
            m.save(out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                if gt.suffix == ".json":
                    _beam_synth_qa.main(out, str(gt))
                else:
                    _beam_qa.main(out, str(gt / "coord.npy"), str(gt / "class.npy"))
            t = buf.getvalue()
            cov = (_num(r"INSTANSSIKATTAVUUS (\d+/\d+)", t) if gt.suffix != ".json"
                   else _num(r"KATTAVUUS.*?([\d.]+)", t))
            rows.append((tag, fr, B._MIN_DEPTH, len(m.beams), cov,
                         _num(r"TARKKUUS.*?([\d.]+)", t)))
            print(f"  {tag} frac={fr:.2f} raja={B._MIN_DEPTH:6.0f}mm "
                  f"palkkeja={len(m.beams):3d} {cov} tark={rows[-1][5]}", flush=True)
    B._MIN_DEPTH = orig

    print("")
    print(f"{'aineisto':14s} {'frac':>5s} {'raja':>7s} {'palkkeja':>8s} "
          f"{'kattavuus':>10s} {'tarkkuus':>8s}")
    for r in rows:
        print(f"{r[0]:14s} {r[1]:5.2f} {r[2]:6.0f}mm {r[3]:8d} {r[4]:>10s} {r[5]:>8s}")


if __name__ == "__main__":
    main()

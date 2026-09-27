"""Erottaako poikkileikkaus kantavan palkin kotelosta?

Nykyiset portit mittaavat POHJAKUVAA: pituus/leveys (`_MIN_ASPECT`). Ne eivat
katso poikkileikkausta lainkaan. Mitattu:

  Rohbaun GT-palkit   leveys/syvyys 0.3-0.8
  liiketilan palkit   0.44
  asunnon ehdokas     2.6   (965 mm levea, 373 mm syva, aspect 3.3 -> lapi)

Kantava palkki on kapea ja syva; levea ja matala kappale katonrajassa on kotelo
tai kanavan verhous. Tama ajaa VAIN detektorin usealla leveys/syvyys-katolla ja
mittaa mita katto maksaa. Jos se poistaa yhdenkin GT-palkin, se on liian tiukka
riippumatta siita mita se tekee asunnolle.

Ajo: _beam_profile_sweep.py [suhde ...]
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
    ratios = [float(v) for v in sys.argv[1:]] or [0.0, 3.0, 2.0, 1.5, 1.2]
    site = Path(str(DATA / "_rohbau" / _SITE))
    cases = [(sc, site / sc / "cloud.ply",
              Path(str(OUTPUT / f"_rohbau_{_SITE}_{sc}" / "floor_00" / "model.json")),
              site / sc)
             for sc in sorted(p.name for p in site.iterdir() if p.is_dir())]
    cases += [("retail_s", Path(str(DATA / "_retail_s.ply")),
               Path(str(OUTPUT / "_2nd_retail_s" / "floor_00" / "model.json")),
               Path(str(DATA / "_retail_s.ply.gt.json"))),
              ("apt", Path(str(DATA / "_apt_merged.ply")),
               Path(str(OUTPUT / "_2nd_apt" / "floor_00" / "model.json")), None)]

    orig = getattr(B, "_MAX_WIDTH_DEPTH", 0.0)
    rows = []
    for tag, cloud_p, mj, gt in cases:
        if not (cloud_p.exists() and mj.exists()):
            print(f"ohitetaan {tag}")
            continue
        pcd = _cloud(cloud_p)
        m = StructuralModel.load(str(mj))
        zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
        zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=None)
        has_ceiling = zc is not None
        if zc is None:
            zc = zf + 3000.0
        for r in ratios:
            B._MAX_WIDTH_DEPTH = r
            m.beams = B.detect_beams(pcd, m.walls, zf, zc, has_ceiling=has_ceiling)
            cov = pre = "-"
            if gt is not None:
                out = str(mj.with_suffix(".prof.json"))
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
                pre = _num(r"TARKKUUS.*?([\d.]+)", t)
            rows.append((tag, r, len(m.beams), cov, pre))
            print(f"  {tag} suhde={r:.1f} palkkeja={len(m.beams):3d} {cov} tark={pre}",
                  flush=True)
    B._MAX_WIDTH_DEPTH = orig

    print("")
    print(f"{'aineisto':14s} {'suhde':>6s} {'palkkeja':>8s} {'kattavuus':>10s} "
          f"{'tarkkuus':>8s}")
    for r in rows:
        print(f"{r[0]:14s} {r[1]:6.1f} {r[2]:8d} {r[3]:>10s} {r[4]:>8s}")
    print("suhde 0 = katto pois paalta.")


if __name__ == "__main__":
    main()

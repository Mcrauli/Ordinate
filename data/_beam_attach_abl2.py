"""Sama `_attached`-ablaatio muilla aineistoilla: synteettinen liiketila + asunto.

Rohbau kertoo mita portti maksaa kattavuudessa. Se ei kerro mita se ESTAA:
portti lisattiin ripustettua kanavaa ja asunnon hormia vastaan. Jos se
poistetaan, harhapalkkien maara naissa on mitattava, ei oletettava.

Ajo: _beam_attach_abl2.py
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

from _paths import DATA, OUTPUT  # noqa: E402

from ordinate.core.segmentation import beam_detector as B  # noqa: E402
from ordinate.schemas.model import StructuralModel  # noqa: E402

_TRUE = lambda *a, **k: True  # noqa: E731
_CASES = [("_retail_s.ply", "_2nd_retail_s", "_retail_s.ply.gt.json"),
          ("_retail_l.ply", "_2nd_retail_l", "_retail_l.ply.gt.json"),
          ("_apt_merged.ply", "_2nd_apt", None)]


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def _model_json(out_dir: Path) -> Path:
    a, b = out_dir / "floor_00" / "model.json", out_dir / "model.json"
    if a.exists() and b.exists():
        return a if a.stat().st_mtime >= b.stat().st_mtime else b
    return a if a.exists() else b


def main() -> None:
    import _beam_synth_qa
    orig = B._attached
    rows = []
    for cloud_name, out_name, gt_name in _CASES:
        cloud = Path(str(DATA / cloud_name))
        mj = _model_json(Path(str(OUTPUT / out_name)))
        if not (cloud.exists() and mj.exists()):
            print(f"ohitetaan {cloud_name}: puuttuu")
            continue
        pts = np.asarray(o3d.io.read_point_cloud(str(cloud)).points, dtype=np.float64)
        if np.ptp(pts[:, 0]) < 500.0:
            pts *= 1000.0
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(pts)
        m = StructuralModel.load(str(mj))
        zf = min((s.elevation for s in m.slabs if s.slab_type == "floor"), default=0.0)
        zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=None)
        has_ceiling = zc is not None
        if zc is None:
            zc = zf + 3000.0
        for on in (True, False):
            B._attached = orig if on else _TRUE
            beams = B.detect_beams(pcd, m.walls, zf, zc, has_ceiling=has_ceiling)
            cov = pre = stray = "-"
            if gt_name:
                m.beams = beams
                out = str(mj.with_suffix(".abl2.json"))
                m.save(out)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    _beam_synth_qa.main(out, str(DATA / gt_name))
                t = buf.getvalue()
                cov = _num(r"KATTAVUUS.*?([\d.]+)", t)
                pre = _num(r"TARKKUUS.*?([\d.]+)", t)
                stray = _num(r"HARHAPALKKEJA (\d+)", t)
            rows.append((cloud_name, "paalla" if on else "pois", len(beams),
                         cov, pre, stray))
            print(f"  {cloud_name} portti={'paalla' if on else 'pois':6s} "
                  f"palkkeja={len(beams)} kattavuus={cov} tarkkuus={pre} "
                  f"harhoja={stray}", flush=True)
    B._attached = orig
    print("")
    print(f"{'aineisto':18s} {'portti':7s} {'palkkeja':>8s} {'kattavuus':>9s} "
          f"{'tarkkuus':>8s} {'harhoja':>7s}")
    for r in rows:
        print(f"{r[0]:18s} {r[1]:7s} {r[2]:8d} {r[3]:>9s} {r[4]:>8s} {r[5]:>7s}")


if __name__ == "__main__":
    main()

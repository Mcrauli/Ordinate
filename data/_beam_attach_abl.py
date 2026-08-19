"""Mita `_attached` oikeasti karsii — ablaatio kaikilla sceneilla.

`_beam_gate_probe.py` mittasi scene_07000:sta etta `_attached` hylkaa 33/75
laikusta, mukaan lukien 20.6 m pitkan 560 mm levean (suhde 37) — eli
yksiselitteisen palkin. Portti lisattiin ripustettua kanavaa vastaan, mutta
asunnon hormin pudotti soffit-ehto, ei tama. Kysymys on siis mitattava, ei
paateltava: paljonko portti maksaa kattavuudessa ja paljonko se tuo
tarkkuudessa.

Ajo: _beam_attach_abl.py [tol ...]      tol = -1 tarkoittaa porttia pois
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

from scan2bim.core.segmentation import beam_detector as B  # noqa: E402
from scan2bim.schemas.model import StructuralModel  # noqa: E402

_SITE = "site_07"
_TRUE = lambda *a, **k: True  # noqa: E731


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def main() -> None:
    tols = [float(v) for v in sys.argv[1:]] or [-1.0, 300.0, 500.0, 800.0, 1200.0]
    site = Path(str(DATA / "_rohbau" / _SITE))
    scenes = [p.name for p in sorted(site.iterdir()) if p.is_dir()]
    orig_attached, orig_tol = B._attached, B._ATTACH

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
        zc = max((s.elevation for s in m.slabs if s.slab_type == "ceiling"), default=None)
        has_ceiling = zc is not None
        if zc is None:
            zc = zf + 3000.0
        for tol in tols:
            B._attached = _TRUE if tol < 0 else orig_attached
            B._ATTACH = orig_tol if tol < 0 else tol
            m.beams = B.detect_beams(pcd, m.walls, zf, zc, has_ceiling=has_ceiling)
            out = str(mj.with_suffix(".abl.json"))
            m.save(out)
            buf = io.StringIO()
            with redirect_stdout(buf):
                _beam_qa.main(out, str(site / sc / "coord.npy"),
                              str(site / sc / "class.npy"))
            t = buf.getvalue()
            rows.append((sc, tol, len(m.beams),
                         _num(r"INSTANSSIKATTAVUUS (\d+/\d+)", t),
                         _num(r"INSTANSSIKATTAVUUS \d+/\d+ = ([\d.]+)", t),
                         _num(r"TARKKUUS.*?([\d.]+)", t)))
            print(f"  {sc} tol={tol:6.0f} -> {rows[-1][3]} tark={rows[-1][5]}",
                  flush=True)
    B._attached, B._ATTACH = orig_attached, orig_tol

    print("")
    print(f"{'scene':14s} {'tol':>6s} {'palkkeja':>8s} {'inst':>8s} "
          f"{'kattavuus':>9s} {'tarkkuus':>8s}")
    for r in rows:
        print(f"{r[0]:14s} {r[1]:6.0f} {r[2]:8d} {r[3]:>8s} {r[4]:>9s} {r[5]:>8s}")
    print("")
    for tol in tols:
        sel = [r for r in rows if r[1] == tol]
        f = sum(int(r[3].split("/")[0]) for r in sel if "/" in r[3])
        n = sum(int(r[3].split("/")[1]) for r in sel if "/" in r[3])
        pr = [float(r[5]) for r in sel if r[5] not in ("-", "")]
        print(f"tol {tol:6.0f}: yhteensa {f}/{n} = {f / max(n, 1):.3f}   "
              f"tarkkuus ka {np.mean(pr) if pr else float('nan'):.3f}")
    print("tol -1 = portti pois paalta.")


if __name__ == "__main__":
    main()

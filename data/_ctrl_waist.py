"""Kontrolli: poistaako vyötärörajattu pintahaku AITOJA seiniä?

Ajaa saman aineiston kahdesti — kerran nykykoodilla, kerran `_nearest_surface`
palautettuna KOKO KORKEUDEN hakuun (tila ennen korjausta) — ja vertaa seinä-
joukkoja. Ero kertoo tarkalleen mitkä seinät korjaus poistaa lisää.

Ajo: .venv/Scripts/python.exe data/_ctrl_waist.py _retail_s
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ordinate.core.qa.deviation as dev  # noqa: E402
from ordinate.core.pipeline import Pipeline, PipelineConfig  # noqa: E402
from _paths import DATA, OUTPUT  # noqa: E402

_NEW = dev._nearest_surface


def _old_nearest_surface(w, pts_all, index):
    """v0.9.18: haku koko korkeudelta, ei jatkuvuusehtoa."""
    p0 = np.array(w.axis[0], float)
    p1 = np.array(w.axis[1], float)
    L = float(np.linalg.norm(p1 - p0))
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    pts = pts_all
    if index is not None:
        from ordinate.core.geometry.xy_index import subset
        pts, _ = subset(pts_all, index, p0, u, n, dev._SUP_SEEK, 0.0, L)
    if len(pts) < dev._SUP_MIN_PTS:
        return None
    rel = pts[:, :2] - p0
    t, perp, z = rel @ u, rel @ n, pts[:, 2]
    sel = ((t > 0.0) & (t < L) & (np.abs(perp) < dev._SUP_SEEK)
           & (z > w.z_min + 100.0) & (z < w.z_min + w.height - 100.0))
    if sel.sum() < dev._SUP_MIN_PTS:
        return None
    hist, edges = np.histogram(perp[sel], bins=40, range=(-dev._SUP_SEEK, dev._SUP_SEEK))
    peak = 0.5 * (edges[hist.argmax()] + edges[hist.argmax() + 1])
    return round(abs(abs(float(peak)) - w.thickness / 2.0), 1)


def run(ply: Path, tag: str) -> list[str]:
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False)
    models = Pipeline(cfg).run_floors([ply], Path(str(OUTPUT / f"_ctrlwaist_{tag}")))
    return [w.id for m in models for w in m.walls]


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "_retail_s"
    ply = Path(str(DATA / f"{name}.ply"))
    if not ply.exists():
        print(f"PUUTTUU {ply}")
        return

    dev._nearest_surface = _old_nearest_surface
    before = run(ply, f"{name}_old")
    dev._nearest_surface = _NEW
    after = run(ply, f"{name}_new")

    lost = [w for w in before if w not in after]
    gained = [w for w in after if w not in before]
    print(f"\n== {name}: ENNEN {len(before)} seinää -> JÄLKEEN {len(after)}")
    print(f"   poistui lisää: {lost or 'ei mitään'}")
    print(f"   tuli lisää   : {gained or 'ei mitään'}")


if __name__ == "__main__":
    main()

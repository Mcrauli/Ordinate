"""Loytyisiko puuttuvat seinat jaannoksesta, kun ehdokkaalta vaaditaan TASO?

`semantics/residual_walls.py` rakennettiin tahan ja kytkettiin pois: ehdokkaista
vain 8/15 oli aitoja ja tarkkuus romahti 0.924 -> 0.515. Syy kirjattiin
AGENTS.md:hen: ehdokkaan on todistettava itsensa jo syntyessaan, eika yksikaan
silloin kokeiltu erottelija (tuki, jatkuvuus, lahisuodatus, pystyulottuvuus,
liittyvyys) pystynyt siihen.

Tasomaisuus on uusi mitattu erottelija — kaistan hajonta on 2-6 mm aidolla
pinnalla ja kymmenia millimetreja putkimassassa. Tama mittaa, erottaisiko se
jaannosehdokkaat, ENNEN kuin residuaalihaku kytketaan takaisin.

Kaytto: _residual_flat_probe.py <model.json> <pilvi.ply> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.geometry.xy_index import XYIndex  # noqa: E402
from ordinate.core.qa.coverage import wallish_points  # noqa: E402
from ordinate.core.semantics.flatness_prune import flat_fraction  # noqa: E402

_CELL = 150.0        # mm — ruudukko lunastamattomien pisteiden ryhmittelyyn
_MIN_LEN = 2000.0    # mm — lyhyempi ei ole ehdokas
_BAND = 80.0


class _Cand:
    def __init__(self, a, b, thickness=200.0):
        self.axis = [list(a), list(b)]
        self.thickness = thickness


def _segments(xy: np.ndarray) -> list:
    """Ryhmittele pisteet yhtenaisiin komponentteihin ja sovita jokaiseen jana."""
    from scipy import ndimage

    ij = np.floor(xy / _CELL).astype(np.int64)
    ij -= ij.min(axis=0)
    grid = np.zeros(ij.max(axis=0) + 1, dtype=bool)
    grid[ij[:, 0], ij[:, 1]] = True
    lab, n = ndimage.label(grid, structure=np.ones((3, 3)))
    idx = lab[ij[:, 0], ij[:, 1]]
    out = []
    for k in range(1, n + 1):
        g = xy[idx == k]
        if len(g) < 30:
            continue
        c = g - g.mean(axis=0)
        w, v = np.linalg.eigh(np.cov(c.T))
        u = v[:, -1]
        s = c @ u
        L = float(s.max() - s.min())
        if L < _MIN_LEN:
            continue
        width = float(4.0 * np.sqrt(max(w[0], 0.0)))
        if width > 400.0:            # ei jana vaan laikku
            continue
        mid = g.mean(axis=0)
        out.append((mid + u * s.min(), mid + u * s.max(), L, width, len(g)))
    return out


def main(model_json: str, cloud_path: str, name: str = "") -> None:
    import open3d as o3d

    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    del pc
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"),
             default=float(np.percentile(pts[:, 2], 1)))
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=float(np.percentile(pts[:, 2], 99)))

    mask, q = wallish_points(pts, zf + 400.0, zc - 300.0)
    W = q[mask][:, :2]
    claimed = np.zeros(len(W), dtype=bool)
    for w in m["walls"]:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 800.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = W - a
        s, t = d @ u, d @ n
        claimed |= ((s > 0) & (s < L)
                    & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND))
    free = W[~claimed]
    print(f"{name}: seinamaisia {len(W):,}, lunastamatta {len(free):,} "
          f"({1 - claimed.mean():.0%})")
    if len(free) < 100:
        return

    cands = _segments(free)
    if not cands:
        print("  ei ehdokkaita")
        return

    lo = zf + 0.25 * (zc - zf)
    hi = zf + 0.75 * (zc - zf)
    band = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]
    p2 = o3d.geometry.PointCloud()
    p2.points = o3d.utility.Vector3dVector(band)
    band = np.asarray(p2.voxel_down_sample(10.0).points)
    del p2
    index = XYIndex(band)

    fr = []
    for a, b, L, width, npts in cands:
        f = flat_fraction(_Cand(a, b), band, index)
        fr.append((L, width, npts, f))
    good = [r for r in fr if r[3] is not None and r[3] >= 0.20]
    tot = sum(r[0] for r in fr) / 1000.0
    gl = sum(r[0] for r in good) / 1000.0
    print(f"  ehdokkaita {len(fr)} ({tot:.0f} m), tasomaisia {len(good)} ({gl:.0f} m)")
    for r in sorted(good, key=lambda r: -r[0])[:8]:
        print(f"    L{r[0]/1000:5.1f} m  leveys {r[1]:5.0f} mm  pisteita {r[2]:5d}  "
              f"tasomaisia {r[3]:.2f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

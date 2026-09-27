"""Mika jaa mallintamatta — ILMAN ground truthia.

`_gap_probe.py` ryhmittelee lunastamattomat GT-seinapisteet, joten se toimii
vain Rohbaulla. Asiakaskohteessa sama kysymys on tarkeampi eika siihen ole
vastausta: kattavuus 0.226 kertoo ETTA jotain puuttuu, ei MITA.

Ottaa `coverage.wallish_points`-maskin, poistaa mallin seinakaistojen
lunastamat, ryhmittelee loput yhtenaisiksi paloiksi ja tulostaa ne
kokojarjestyksessa. Iso yhtenainen pala = kokonainen seina jota ei mallinnettu;
sirpaleet = reunoja ja kohinaa.

Kaytto: _gap_nogt.py <model.json> <pilvi> [out.png]
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from scan2bim.core.qa.coverage import wallish_points  # noqa: E402

_BAND = 80.0
_MIN_WALL_LEN = 800.0
_CELL = 400.0          # mm — ryhmittelyruutu
_MIN_PIECE_M2 = 2.0    # m² — tata pienempi pala on kohinaa


def _claimed(model: dict, xy: np.ndarray) -> np.ndarray:
    out = np.zeros(len(xy), dtype=bool)
    for w in model["walls"]:
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < _MIN_WALL_LEN:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        out |= (s > 0) & (s < L) & (np.abs(np.abs(t) - w["thickness"] / 2.0) < _BAND)
    return out


def main(model_path: str, cloud_path: str, out_png: str | None = None) -> None:
    import open3d as o3d
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components

    model = json.loads(pathlib.Path(model_path).read_text(encoding="utf-8"))
    pts = np.asarray(o3d.io.read_point_cloud(cloud_path).points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    zf = min((s["elevation"] for s in model["slabs"] if s["slab_type"] == "floor"),
             default=float(pts[:, 2].min()))
    zc = max((s["elevation"] for s in model["slabs"] if s["slab_type"] == "ceiling"),
             default=float(pts[:, 2].max()))

    is_wall, q = wallish_points(pts, zf + 400.0, zc - 300.0)
    claimed = _claimed(model, q[:, :2])
    missing = is_wall & ~claimed
    print(f"seinamaisia pystypintoja {int(is_wall.sum()):,}, "
          f"mallin kattamia {int((is_wall & claimed).sum()):,}, "
          f"PUUTTUU {int(missing.sum()):,} ({100*missing.sum()/max(is_wall.sum(),1):.1f} %)")
    if not missing.any():
        return

    ij = np.floor(q[missing][:, :2] / _CELL).astype(np.int64)
    cells, inv = np.unique(ij, axis=0, return_inverse=True)
    lookup = {(int(a), int(b)): n for n, (a, b) in enumerate(cells)}
    rows, cols = [], []
    for n, (a, b) in enumerate(cells):
        for da, db in ((1, 0), (0, 1), (1, 1), (1, -1)):
            m = lookup.get((int(a) + da, int(b) + db))
            if m is not None:
                rows.append(n)
                cols.append(m)
    if rows:
        g = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(cells), len(cells)))
        n_comp, label = connected_components(g, directed=False)
    else:
        n_comp, label = len(cells), np.arange(len(cells))

    cell_m2 = (_CELL / 1000.0) ** 2
    pieces = []
    for c in range(n_comp):
        m = label == c
        area = int(m.sum()) * cell_m2
        if area < _MIN_PIECE_M2:
            continue
        cc = cells[m].astype(np.float64) * _CELL / 1000.0
        span = float(np.ptp(cc @ np.linalg.svd(cc - cc.mean(0), full_matrices=False)[2][0]))
        pieces.append((area, span, cc.mean(0)))
    pieces.sort(reverse=True, key=lambda p: p[0])
    print(f"\npaloja joiden ala >= {_MIN_PIECE_M2} m2: {len(pieces)}")
    print(f"{'ala m2':>8s} {'pituus m':>9s}   keskipiste (m)")
    for area, span, mid in pieces[:15]:
        print(f"{area:8.1f} {span:9.1f}   ({mid[0]:.0f}, {mid[1]:.0f})")
    tot = sum(p[0] for p in pieces)
    print(f"\nyhteensa {tot:.0f} m2 mallintamatonta seinapintaa "
          f"{len(pieces)} palassa")

    if out_png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 10), facecolor="white")
        kept = q[is_wall & claimed]
        ax.scatter(kept[:, 0] / 1000, kept[:, 1] / 1000, s=0.5, c="#b8b8b8",
                   linewidths=0, label="mallinnettu")
        miss = q[missing]
        ax.scatter(miss[:, 0] / 1000, miss[:, 1] / 1000, s=0.7, c="#d81e2c",
                   linewidths=0, label="PUUTTUU")
        ax.set_aspect("equal")
        ax.legend(loc="upper right")
        ax.set_title(f"Mallintamatta {100*missing.sum()/max(is_wall.sum(),1):.0f} % "
                     f"pystypinnoista")
        fig.savefig(out_png, dpi=110, bbox_inches="tight")
        print("kirjoitettu", out_png)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2] if len(a) > 2 else None)

"""Kontaktiarkki seinien labelointiin: aito vai ei, kuvista katsottuna.

Per-projekti-oppiminen tarvitsee seinatason kylla/ei-labelit, ei per-piste-
labelointia CloudComparessa. Tama piirtaa jokaisesta mallin seinasta kaksi
nakymaa samalle arkille numeroituna, jotta 244 seinaa voi kayda lapi
selaamalla eika raahaamalla pistepilvea.

Kaksi nakymaa per seina, koska yksi ei riita erottamaan HAAMUA (ei mitaan)
SIIRTYNEESTA (pinta on, mutta sivussa) — sama syy kuin `_wall_view.py`:ssa:
  vasen  = XY vyotarolta, malli punaisella, pilvi harmaana
  oikea  = poikkileikkaus (etaisyys akselista vs korkeus)

Kaytto:
  _wall_sheet.py <model.json> <pilvi.ply> <out_dir> [--per-page 12]

Tulos: out_dir/sheet_00.png … ja out_dir/walls.json (indeksi -> seinan id).
Labelit kirjataan sen jalkeen: _wall_labels.py <out_dir> "3 7 12 40-45"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def _load_pts(p: Path) -> np.ndarray:
    if p.suffix.lower() == ".npy":
        a = np.load(p).astype(np.float64)
    else:
        import open3d as o3d
        a = np.asarray(o3d.io.read_point_cloud(str(p)).points)
    if len(a) and float(np.ptp(a[:, 0])) < 500.0:
        a = a * 1000.0
    return a


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    per_page = 12
    if "--per-page" in sys.argv:
        per_page = int(sys.argv[sys.argv.index("--per-page") + 1])
    model_json, cloud, out = Path(args[0]), Path(args[1]), Path(args[2])
    out.mkdir(parents=True, exist_ok=True)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.spatial import cKDTree

    W = json.loads(model_json.read_text(encoding="utf-8"))["walls"]
    P = _load_pts(cloud)
    z0 = float(np.percentile(P[:, 2], 2))
    z1 = float(np.percentile(P[:, 2], 98))
    lo, hi = z0 + 0.25 * (z1 - z0), z0 + 0.75 * (z1 - z0)
    band = P[(P[:, 2] > lo) & (P[:, 2] < hi)]
    print(f"{len(W)} seinaa, vyotarokaista {len(band):,} pistetta", flush=True)
    tree = cKDTree(band[:, :2])

    index = []
    pages = (len(W) + per_page - 1) // per_page
    for pg in range(pages):
        sel = W[pg * per_page:(pg + 1) * per_page]
        rows = len(sel)
        fig, axes = plt.subplots(rows, 2, figsize=(9.0, 1.5 * rows),
                                 gridspec_kw={"width_ratios": [2, 1]})
        axes = np.atleast_2d(axes)
        for r, w in enumerate(sel):
            k = pg * per_page + r
            a = np.asarray(w["axis"][0], float)[:2]
            b = np.asarray(w["axis"][-1], float)[:2]
            L = float(np.linalg.norm(b - a))
            u = (b - a) / max(L, 1e-6)
            n = np.array([-u[1], u[0]])
            c = 0.5 * (a + b)
            idx = tree.query_ball_point(c, r=L / 2 + 1800.0)
            Q = band[idx] if idx else np.empty((0, 3))
            axL, axR = axes[r, 0], axes[r, 1]
            if len(Q):
                d = Q[:, :2] - a
                t, perp = d @ u, d @ n
                m = (t > -900.0) & (t < L + 900.0) & (np.abs(perp) < 1800.0)
                axL.scatter(t[m], perp[m], s=0.25, c="0.55", lw=0)
                axR.scatter(perp[m], Q[m][:, 2], s=0.25, c="0.55", lw=0)
            axL.plot([0, L], [0, 0], "r-", lw=1.6)
            axL.set_xlim(-900, L + 900); axL.set_ylim(-1800, 1800)
            axR.axvline(0, color="r", lw=1.2); axR.set_xlim(-1800, 1800)
            th = float(w.get("thickness") or 200.0)
            axL.set_title(f"[{k}] {w['id']}  {L/1000:.1f} m  t={th:.0f} mm  "
                          f"tuki={w.get('support')}", fontsize=6, loc="left")
            for ax in (axL, axR):
                ax.set_xticks([]); ax.set_yticks([])
            index.append({"i": k, "id": w["id"], "len_mm": round(L, 1)})
        plt.tight_layout()
        f = out / f"sheet_{pg:02d}.png"
        plt.savefig(f, dpi=110); plt.close(fig)
        print(f"  {f.name}  seinat {pg*per_page}..{pg*per_page+rows-1}", flush=True)
    (out / "walls.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"valmis: {pages} sivua, indeksi {out/'walls.json'}")


if __name__ == "__main__":
    main()

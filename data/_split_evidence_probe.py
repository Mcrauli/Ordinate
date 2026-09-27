"""Mika todiste pitaa kellarin ristikkoseinat kasassa?

`split_walls_at_gaps` katsoo onko 500 mm sarakkeessa >=4 pistetta 150 mm
kaistassa. Kellarissa joka sarakkeessa on jotain (putki, kanava, kaapeli), eli
ehto on aina tosi eika mikaan katkea. Tama mittaa saman sarakkeen kahdella
todisteella rinnakkain:

  any     = mika tahansa piste kaistassa (nykyinen saanto)
  wallish = piste jonka normaali on vaakasuora JA jonka XY-solussa pystypintaa
            yli puolet kaistan korkeudesta (sama maaritelma kuin qa/coverage)

Kaytto: _split_evidence_probe.py <model.json> <pilvi.ply> [cache.npz]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.qa.coverage import wallish_points  # noqa: E402

_COL = 500.0
_BAND = 150.0
_MIN_PTS = 4


def _cols(pts, a, u, n, half, length, n_col):
    d = pts[:, :2] - a
    s, t = d @ u, d @ n
    on = (np.abs(np.abs(t) - half) < _BAND) & (s > -_COL) & (s < length + _COL)
    if not on.any():
        return np.zeros(n_col, dtype=int)
    idx = np.clip((s[on] / _COL).astype(int), 0, n_col - 1)
    return np.bincount(idx, minlength=n_col)


def main(model_json: str, cloud_path: str, cache: str | None = None) -> None:
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    walls = m["walls"]
    floor_z = min((s["elevation"] for s in m.get("slabs", []) if s.get("slab_type") == "floor"),
                  default=None)
    ceil_z = max((s["elevation"] for s in m.get("slabs", []) if s.get("slab_type") == "ceiling"),
                 default=None)

    cp = Path(cache) if cache else None
    if cp is not None and cp.exists():
        z = np.load(cp)
        q, is_wall, floor_z, ceil_z = z["q"], z["m"], float(z["fz"]), float(z["cz"])
        print(f"cache: {cp}")
    else:
        import open3d as o3d
        pc = o3d.io.read_point_cloud(cloud_path)
        pts = np.asarray(pc.points)
        del pc
        if np.ptp(pts[:, 0]) < 500.0:     # metrit -> mm, sama saanto kuin loaderissa
            pts = pts * 1000.0
        if floor_z is None:
            floor_z, ceil_z = np.percentile(pts[:, 2], 1), np.percentile(pts[:, 2], 99)
        print(f"pilvi {len(pts):,}  lattia {floor_z:.0f}  katto {ceil_z:.0f}")
        is_wall, q = wallish_points(pts, floor_z + 400.0, ceil_z - 300.0)
        del pts
        if cp is not None:
            np.savez_compressed(cp, q=q.astype(np.float32), m=is_wall,
                                fz=floor_z, cz=ceil_z)
    print(f"harvennettu {len(q):,}  seinamaisia {int(is_wall.sum()):,} "
          f"({is_wall.mean():.1%})")

    wq = q[is_wall]
    rows = []
    for w in walls:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], dtype=float)[:2]
        b = np.asarray(ax[-1], dtype=float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1000.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        half = float(w.get("thickness", 200.0)) / 2.0
        n_col = max(int(L / _COL), 1)
        c_any = _cols(q, a, u, n, half, L, n_col)
        c_wal = _cols(wq, a, u, n, half, L, n_col)
        fill = c_wal >= 1
        runs, r = [], 0
        for f in list(fill) + [True]:
            if f:
                if r:
                    runs.append(r)
                r = 0
            else:
                r += 1
        longest = max(runs, default=0) * _COL
        in_big = sum(x for x in runs if x * _COL >= 2000.0) * _COL
        ev, e = [], 0
        for f in list(fill) + [False]:
            if f:
                e += 1
            else:
                if e:
                    ev.append(e)
                e = 0
        rows.append((w["id"], L,
                     float((c_any >= _MIN_PTS).mean()),
                     float(fill.mean()), longest, in_big / L,
                     max(ev, default=0) * _COL, len(ev)))

    if not rows:
        print("ei seinia")
        return
    L = np.array([r[1] for r in rows])
    fa = np.array([r[2] for r in rows])
    fw = np.array([r[3] for r in rows])
    gap = np.array([r[4] for r in rows])
    big = np.array([r[5] for r in rows])
    print()
    print(f"seinia {len(rows)}  yhteispituus {L.sum()/1000:.0f} m")
    print(f"{'':22s} {'p10':>6s} {'med':>6s} {'p90':>6s}  {'<0.30':>6s}")
    for name, v in (("kate any (nykyinen)", fa), ("kate wallish", fw)):
        print(f"{name:22s} {np.percentile(v,10):6.2f} {np.median(v):6.2f} "
              f"{np.percentile(v,90):6.2f}  {float((v<0.30).mean()):6.2f}")
    print(f"{'pisin tyhja jakso mm':22s} {np.percentile(gap,10):6.0f} "
          f"{np.median(gap):6.0f} {np.percentile(gap,90):6.0f}")
    print(f"{'osuus >=2 m aukoissa':22s} {np.percentile(big,10):6.2f} "
          f"{np.median(big):6.2f} {np.percentile(big,90):6.2f}")
    ev = np.array([r[6] for r in rows])
    nr = np.array([r[7] for r in rows])
    print(f"{'pisin todistejakso mm':22s} {np.percentile(ev,10):6.0f} "
          f"{np.median(ev):6.0f} {np.percentile(ev,90):6.0f}")
    print(f"{'todistejaksoja kpl':22s} {np.percentile(nr,10):6.1f} "
          f"{np.median(nr):6.1f} {np.percentile(nr,90):6.1f}")
    print()
    print(f"seinia joilla any=1.00 mutta wallish<0.30: "
          f"{int(((fa > 0.99) & (fw < 0.30)).sum())}")
    print(f"pituutta niissa: {L[(fa > 0.99) & (fw < 0.30)].sum()/1000:.0f} m")
    print()
    print("pisimmat 12 (id, pit m, any, wallish, aukko, >=2m, jakso, kpl):")
    for i in np.argsort(-L)[:12]:
        print(f"  {rows[i][0]:24s} {L[i]/1000:6.1f} {fa[i]:5.2f} {fw[i]:5.2f}"
              f" {gap[i]/1000:7.1f} {big[i]:6.2f} {ev[i]/1000:7.1f} {nr[i]:4d}")


if __name__ == "__main__":
    main(*sys.argv[1:])

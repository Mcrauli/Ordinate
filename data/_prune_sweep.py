"""Semanttisen karsinnan kynnyssweep ILMAN putkiajoa.

`prune_non_wall_surfaces` poistaa seinan jonka kaistassa alle `_MIN_FRAC`
pisteista on suodattimen mukaan seinaa. Kellarissa se poisti 21 seinaa 270:sta,
vaikka mitattu jakauma sanoo etta 124/304 jaa alle 0.30 — ero tulee
todisteehdosta (>=50 luokiteltua pistetta kaistassa).

Tama ajaa saman saannon valmiille mallille eri kynnyksilla ja laskee
kattavuuden ja tarkkuuden `qa/coverage`-maaritelmalla (sama kuin
`_wall_coverage_nogt`), joten sweep maksaa sekunteja eika 36 minuuttia.

Kaytto: _prune_sweep.py <model.json> <wallish.npz> <sem.npz> [ulos.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.semantics import semantic_prune as SP  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _sem_cache import load as load_sem  # noqa: E402

_BAND = 80.0            # sama kuin qa/coverage._BAND
_MIN_WALL_LEN = 800.0


def _claim(walls, xy):
    claimed = np.zeros(len(xy), dtype=bool)
    for w in walls:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < _MIN_WALL_LEN:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        claimed |= ((s > 0) & (s < L)
                    & (np.abs(np.abs(t) - w.get("thickness", 200.0) / 2.0) < _BAND))
    return claimed


def _score(walls, xy, is_wall):
    c = _claim(walls, xy)
    hit = int((c & is_wall).sum())
    return (hit / max(int(is_wall.sum()), 1), hit / max(int(c.sum()), 1))


def main(model_json: str, wallish_npz: str, sem_npz: str, out: str | None = None) -> None:
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    walls = m["walls"]
    z = np.load(wallish_npz)
    q, is_wall = z["q"].astype(np.float64), z["m"]
    xy = q[:, :2]
    lab = load_sem(sem_npz)

    cov, pre = _score(walls, xy, is_wall)
    print(f"seinia {len(walls)}  kattavuus {cov:.3f}  tarkkuus {pre:.3f}")

    z_min = min((w["z_min"] for w in walls), default=float(q[:, 2].min()))
    height = max((w["height"] for w in walls), default=0.0)
    lo = z_min + SP._WAIST_LO * height
    hi = z_min + SP._WAIST_HI * height
    band = q[(q[:, 2] > lo) & (q[:, 2] < hi)]
    print(f"vyotarokaista {lo:.0f}..{hi:.0f} mm, {len(band):,} pistetta")
    pred = lab.lookup(band)
    bxy = band[:, :2]

    frac, npts = {}, {}
    for w in walls:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < SP._MIN_LEN:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = bxy - a
        s, t = d @ u, d @ n
        sel = ((s > 0) & (s < L)
               & (np.abs(np.abs(t) - w["thickness"] / 2.0) < SP._BAND_MM))
        seen = pred[sel]
        known = seen[seen >= 0]
        npts[w["id"]] = len(known)
        if len(known):
            frac[w["id"]] = float(np.isin(known, SP._WALLISH).mean())

    fv = np.array(list(frac.values()))
    nv = np.array(list(npts.values()))
    print(f"tuomittavia seinia {len(frac)}  luokiteltuja pisteita kaistassa "
          f"p10 {np.percentile(nv,10):.0f} med {np.median(nv):.0f}")
    print(f"seinaosuus p10 {np.percentile(fv,10):.2f} med {np.median(fv):.2f} "
          f"p90 {np.percentile(fv,90):.2f}")

    print()
    print(f"{'kynnys':>7s} {'minpts':>7s} {'poistuu':>8s} {'jaljella':>9s} "
          f"{'kattav':>7s} {'tarkk':>7s}")
    rows = []
    for min_pts in (SP._MIN_PTS, 8):
        for thr in (0.30, 0.40, 0.50, 0.60, 0.70):
            drop = {k for k, v in frac.items()
                    if v < thr and npts[k] >= min_pts}
            keep = [w for w in walls if w["id"] not in drop]
            c2, p2 = _score(keep, xy, is_wall)
            rows.append({"thr": thr, "min_pts": min_pts, "drop": len(drop),
                         "walls": len(keep), "cov": round(c2, 3), "pre": round(p2, 3)})
            print(f"{thr:7.2f} {min_pts:7d} {len(drop):8d} {len(keep):9d} "
                  f"{c2:7.3f} {p2:7.3f}")
    if out:
        Path(out).write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])

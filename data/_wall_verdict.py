"""Jokainen mallin seina kolmeen luokkaan: haamu, siirtynyt vai osuva.

`_wall_view.py` erottaa saman kahdesta seinasta kuvina; tama tekee sen koko
mallille luvuiksi, jotta 160 seinaa voi kayda lapi kerralla.

  osuva     : seinamaista pystypintaa sen omalla pinnalla (|t| ~ paksuus/2)
  siirtynyt : pintaa loytyy mutta vaaralta etaisyydelta (|t| 150..600 mm)
  haamu     : ei pystypintaa lainkaan +-600 mm:n sisalla

Kaytto: _wall_verdict.py <model.json> <wallish.npz>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_FAR = 600.0
_ON = 80.0
_MIN_LEN = 800.0


def main(model_json: str, wallish_npz: str) -> None:
    z = np.load(wallish_npz)
    w = z["q"].astype(np.float64)[z["m"]]
    xy = w[:, :2]
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))

    rows = []
    for x in m["walls"]:
        ax = x.get("axis") or []
        if len(ax) < 2:
            continue
        a = np.asarray(ax[0], float)[:2]
        b = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < _MIN_LEN:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        near = (s > 0) & (s < L) & (np.abs(t) < _FAR)
        half = x["thickness"] / 2.0
        on = near & (np.abs(np.abs(t) - half) < _ON)
        # osuus pituudesta jolla on pintaa omalla pinnalla (500 mm sarakkeet)
        ncol = max(int(L / 500.0), 1)
        cov = 0.0
        if on.any():
            idx = np.clip((s[on] / 500.0).astype(int), 0, ncol - 1)
            cov = float(len(np.unique(idx))) / ncol
        rows.append({
            "id": x["id"], "L": L, "th": x["thickness"], "cov": cov,
            "n_near": int(near.sum()),
            "med_t": float(np.median(np.abs(t[near]))) if near.any() else None,
        })

    n = len(rows)
    ghost = [r for r in rows if r["n_near"] < 30]
    hit = [r for r in rows if r not in ghost and r["cov"] >= 0.30]
    shift = [r for r in rows if r not in ghost and r not in hit]
    tot = sum(r["L"] for r in rows) / 1000.0
    print(f"seinia {n}  yhteispituus {tot:.0f} m")
    for name, g in (("osuva", hit), ("siirtynyt", shift), ("haamu", ghost)):
        ln = sum(r["L"] for r in g) / 1000.0
        print(f"  {name:10s} {len(g):4d} kpl  {ln:6.0f} m  ({ln/max(tot,1):.0%})")
    if shift:
        mt = np.array([r["med_t"] for r in shift if r["med_t"] is not None])
        th = np.array([r["th"] for r in shift])
        print(f"  siirtyneiden pinnan |t| med {np.median(mt):.0f} mm, "
              f"mallin paksuus/2 med {np.median(th)/2:.0f} mm")
    print()
    print(f"  {'id':22s} {'L m':>6s} {'paks':>5s} {'kate':>5s} {'|t|':>6s}")
    for r in sorted(rows, key=lambda r: -r["L"])[:15]:
        print(f"  {r['id']:22s} {r['L']/1000:6.1f} {r['th']:5.0f} {r['cov']:5.2f} "
              f"{(r['med_t'] if r['med_t'] is not None else -1):6.0f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

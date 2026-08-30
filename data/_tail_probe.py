"""Kuinka paljon seinaa on VIIMEISEN todisteen ULKOPUOLELLA?

Tarkkuus 0.194 ja "94 % seinista oman pintansa paalla" eivat ole ristiriita:
seina voi koskettaa pintaa jossain ja silti olla enimmakseen tyhjan paalla.
Talloin vika on PITUUDESSA. Oviaukko on seinan KESKELLA, joten paiden
leikkaaminen on turvallisempaa kuin pilkkominen.

Sokeusehto sama kuin kontrastiportissa: jos seinan ymparistossa ei ole
seinamaista pintaa lainkaan, mittari ei tieda mitaan eika saa leikata.

Kaytto: _tail_probe.py <model.json> <wallish.npz> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_ON = 80.0
_NEAR = 3000.0
_POWER_FRAC = 0.10
_MIN_LEN = 2000.0


def main(model_json: str, wallish_npz: str, name: str = "") -> None:
    z = np.load(wallish_npz)
    q = z["q"].astype(np.float64)
    W = q[z["m"]][:, :2]
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
        half = float(x["thickness"]) / 2.0
        d = W - a
        s, t = d @ u, d @ n
        at = np.abs(t)
        span = (s > -1000.0) & (s < L + 1000.0)
        near = int((span & (at < _NEAR)).sum())
        on = span & (np.abs(at - half) < _ON) & (s > 0) & (s < L)
        if on.any():
            lo, hi = float(s[on].min()), float(s[on].max())
        else:
            lo, hi = L, 0.0
        rows.append((x["id"], L, max(lo, 0.0), max(L - hi, 0.0), near / (L / 1000.0)))

    if not rows:
        print(f"{name}: ei mitattavia")
        return
    dens = np.array([r[4] for r in rows])
    ref = float(np.median(dens))
    judged = [r for r in rows if r[4] >= _POWER_FRAC * ref]
    tot = sum(r[1] for r in rows) / 1000.0
    tail = sum(min(r[2] + r[3], r[1]) for r in judged) / 1000.0
    print(f"{name or model_json:14s} seinia {len(rows):4d} ({len(judged)} tuomittavaa)  "
          f"pituus {tot:6.0f} m  todisteen ulkopuolella {tail:6.0f} m ({tail/max(tot,1):.0%})")
    big = sorted(judged, key=lambda r: -(r[2] + r[3]))[:5]
    for r in big:
        print(f"    {r[0]:22s} L{r[1]/1000:6.1f}  alkupaa {r[2]/1000:5.1f} m  "
              f"loppupaa {r[3]/1000:5.1f} m")


if __name__ == "__main__":
    main(*sys.argv[1:])

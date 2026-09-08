"""Onko seinan ymparistossa TOISTUVA rakenne? Kaluste on jaksollinen, seina ei.

Kalustetyngille ei ole loytynyt erottelijaa: tasomaisuus, kontrasti, tuki,
jatkuvuus ja reunahajonta mittaavat kaikki TASOA, ja taso riippuu
keilausgeometriasta. Jaksollisuus on eri laji — se on suhde saman pilven
sisalla eika riipu siita miten hyvin kohde on keilattu.

Myymalakaluste seisoo rivissa: gondolit 3.2-4.2 m valein, lavahyllyt 3 m
valein. Aito seina ei toistu tasavalein. Tama mittaa sen seinan
KOHTISUORASTA tiheysprofiilista: profiilin autokorrelaatio 2-6 m viiveilla.

Mittaa vain — ei muuta mitaan.

Kaytto: _periodic_probe.py <model.json> <scene_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

FACE = {5, 6, 8, 15}
_REACH = 12_000.0      # mm — nain kauas sivuun
_BIN = 100.0           # mm
_LAG_LO, _LAG_HI = 2_000.0, 6_500.0
_WAIST = (0.30, 0.70)


def _periodicity(w, P) -> tuple[float, float]:
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][-1], float)[:2]
    L = float(np.linalg.norm(b - a))
    if L < 500.0:
        return -1.0, -1.0
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    zlo, zhi = z0 + _WAIST[0] * h, z0 + _WAIST[1] * h
    d = P[:, :2] - a
    t, perp, z = d @ u, d @ n, P[:, 2]
    m = (t > -500.0) & (t < L + 500.0) & (np.abs(perp) < _REACH) & (z > zlo) & (z < zhi)
    if int(m.sum()) < 2000:
        return -1.0, -1.0
    nb = int(2 * _REACH / _BIN)
    hist, _ = np.histogram(perp[m], bins=nb, range=(-_REACH, _REACH))
    x = hist.astype(float) - hist.mean()
    if not np.any(x):
        return -1.0, -1.0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac = ac / ac[0]
    lo, hi = int(_LAG_LO / _BIN), int(_LAG_HI / _BIN)
    seg = ac[lo:hi]
    if not len(seg):
        return -1.0, -1.0
    k = int(np.argmax(seg))
    return float(seg[k]), float((lo + k) * _BIN)


def _truth(w, P, C) -> float:
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][-1], float)[:2]
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    th = float(w.get("thickness") or 200.0)
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    d = P[:, :2] - a
    t, perp, z = d @ u, d @ n, P[:, 2]
    m = ((t > 0) & (t < L) & (np.abs(np.abs(perp) - th / 2.0) < 60.0)
         & (z > z0 + 300.0) & (z < z0 + h - 300.0))
    return float(np.isin(C[m], list(FACE)).mean()) if m.sum() > 100 else -1.0


def _auc(pos, neg) -> float:
    if not pos or not neg:
        return float("nan")
    p, n = np.asarray(pos, float), np.asarray(neg, float)
    return float((p[:, None] > n[None, :]).mean() + 0.5 * (p[:, None] == n[None, :]).mean())


def main(model_json: str, scene: str) -> None:
    W = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    d = Path(scene)
    P = np.load(d / "coord.npy").astype(np.float64)
    if float(np.ptp(P[:, 0])) < 500.0:
        P = P * 1000.0
    C = np.load(d / "class.npy")
    rows = []
    for w in W:
        tr = _truth(w, P, C)
        if tr < 0:
            continue
        ac, lag = _periodicity(w, P)
        if ac < 0:
            continue
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][-1], float)[:2]
        rows.append((float(np.linalg.norm(b - a)) / 1000.0, ac, lag, tr))
    print(f"{'pituus':>7} {'jaksol':>7} {'jakso mm':>9}  GT")
    for L, ac, lag, tr in sorted(rows, key=lambda r: -r[3]):
        print(f"{L:6.1f} m {ac:7.3f} {lag:9.0f}  {tr:.2f}")
    real = [r for r in rows if r[3] >= 0.5]
    fake = [r for r in rows if r[3] < 0.5]
    print(f"\naitoja {len(real)}  valeita {len(fake)}")
    if real and fake:
        pv = [r[1] for r in real]
        nv = [r[1] for r in fake]
        print(f"  jaksollisuus  aito med {np.median(pv):.3f}   vale med "
              f"{np.median(nv):.3f}   AUC(vale>aito) {_auc(nv, pv):.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

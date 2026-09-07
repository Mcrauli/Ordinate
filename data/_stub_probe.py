"""Mika erottaa AIDON seinan KALUSTEEN kylkeen syntyneesta tyngasta?

Keilatussa myymalassa (`_synth_store.py`) putki antaa 43 seinaa kymmenelle
GT-seinalle. Kaikki 33 ylimaaraista ovat 1.0-2.9 m tynkia joiden kaistassa on
100 % kalustepisteita — eivatka ne ole hyllynetupintoja vaan lavahyllyjen ja
gondolien PAATYJA. Se on eri vikamuoto kuin okkluusiottomassa aineistossa.

Tama mittaa ehdokassignaalit molemmille populaatioille GT-totuutta vasten.
Mittaa vain — ei muuta mitaan.

Kaytto: _stub_probe.py <model.json> <scene_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

FACE = {5, 6, 8, 15}


def _signals(w, P, C):
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][-1], float)[:2]
    L = float(np.linalg.norm(b - a))
    if L < 500.0:
        return None
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    th = float(w.get("thickness") or 200.0)
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    d = P[:, :2] - a
    t, perp, z = d @ u, d @ n, P[:, 2]
    box = ((t > 0.0) & (t < L) & (np.abs(perp) < th / 2.0 + 1400.0)
           & (z > z0 + 300.0) & (z < z0 + h - 300.0))
    if box.sum() < 200:
        return None
    t_b, perp_b, z_b, c_b = t[box], perp[box], z[box], C[box]

    face = np.abs(np.abs(perp_b) - th / 2.0) < 60.0
    if face.sum() < 100:
        return None
    truth = float(np.isin(c_b[face], list(FACE)).mean())

    zf = z_b[face]
    htop = float(np.percentile(zf, 98) - z0)
    hspan = float(np.percentile(zf, 98) - np.percentile(zf, 2))

    sign = 1.0 if np.median(perp_b[face]) > 0 else -1.0
    behind = ((sign * perp_b < -(th / 2.0 + 150.0))
              & (sign * perp_b > -(th / 2.0 + 1300.0)))
    front = ((sign * perp_b > th / 2.0 + 150.0)
             & (sign * perp_b < th / 2.0 + 1300.0))
    nb, nf = int(behind.sum()), int(front.sum())
    body = nb / max(nb + nf, 1)

    cols = np.clip(((t_b[face] / L) * 12).astype(int), 0, 11)
    tops = np.array([np.percentile(zf[cols == i], 95) if (cols == i).sum() > 20
                     else np.nan for i in range(12)])
    top_var = float(np.nanstd(tops)) if np.isfinite(tops).sum() > 3 else -1.0

    return {"len": L / 1000.0, "htop": htop, "hspan": hspan, "body": body,
            "topvar": top_var, "truth": truth}


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
        s = _signals(w, P, C)
        if s:
            rows.append(s)
    print(f"{'pituus':>7} {'htop':>7} {'hspan':>7} {'runko':>6} {'topvar':>7}  GT")
    for s in sorted(rows, key=lambda r: -r["truth"]):
        print(f"{s['len']:6.1f} m {s['htop']:7.0f} {s['hspan']:7.0f} "
              f"{s['body']:6.2f} {s['topvar']:7.0f}  {s['truth']:.2f}")
    real = [s for s in rows if s["truth"] >= 0.5]
    fake = [s for s in rows if s["truth"] < 0.5]
    print(f"\naitoja {len(real)}  valeita {len(fake)}")
    for k in ("len", "htop", "hspan", "body", "topvar"):
        pv = [s[k] for s in real]
        nv = [s[k] for s in fake]
        print(f"  {k:7s} aito med {np.median(pv):8.2f}   vale med {np.median(nv):8.2f}"
              f"   AUC {_auc(pv, nv):.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

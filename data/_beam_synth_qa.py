"""Palkit synteettista GT:ta vasten (`_synth_retail.py` -> `.gt.json`).

Rohbau antaa per-piste-GT:n mutta sen palkit ovat 2.5-5.5 m leveita jattilaisia.
Tavallisen kokoluokan palkeista (300 mm) totuus on vain synteettisessa
liiketilassa, ja ilman sita ei tiedeta menettaako sadanto ne.

KATTAVUUS  : kuinka suuri osa GT-palkin akselista on jonkin mallin palkin alla.
TARKKUUS   : kuinka suuri osa mallin palkkien akselipituudesta osuu GT-palkille.

Ajo: _beam_synth_qa.py <model.json> <cloud.ply.gt.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_STEP = 100.0        # mm — akselin naytteistys
_LAT = 500.0         # mm — sallittu sivupoikkeama
_Z = 400.0           # mm — sallittu alapintapoikkeama


def _seg(axis):
    a = np.array(axis[0][:2], float)
    b = np.array(axis[1][:2], float)
    return a, b, float(np.linalg.norm(b - a))


def _samples(a, b, L):
    n = max(int(L / _STEP), 2)
    t = np.linspace(0.0, 1.0, n)
    return a + np.outer(t, b - a), L / n


def _near(p, a, b, L, half):
    u = (b - a) / max(L, 1e-9)
    d = p - a
    s = np.clip(d @ u, 0.0, L)
    perp = d - np.outer(s, u)
    return np.hypot(perp[:, 0], perp[:, 1]) <= half


def main(model_json: str, gt_json: str) -> None:
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    gt = json.loads(Path(gt_json).read_text(encoding="utf-8"))
    gtb = gt.get("beams", [])
    mb = m.get("beams", [])
    print(f"GT-palkkeja {len(gtb)}  mallin palkkeja {len(mb)}")
    if not gtb:
        return

    det = []
    for b in mb:
        a, q, L = _seg(b["axis"])
        soffit = b["axis"][0][2] - b["profile"]["height"] / 2.0
        det.append((a, q, L, soffit, b))

    cov_tot = cov_hit = 0.0
    print(f"\n{'GT-palkki':22s} {'pituus':>7s} {'katettu':>8s} {'lev':>5s}->{'mit':>5s} "
          f"{'syv':>5s}->{'mit':>5s}")
    for g in gtb:
        a, b, L = _seg(g["axis"])
        P, step = _samples(a, b, L)
        hit = np.zeros(len(P), bool)
        w_meas, d_meas = [], []
        for da, dq, dL, dsof, db in det:
            if abs(dsof - g["soffit_z"]) > _Z:
                continue
            h = _near(P, da, dq, dL, _LAT)
            if h.any():
                w_meas.append(db["profile"]["width"])
                d_meas.append(db["profile"]["height"])
            hit |= h
        cov_tot += L
        cov_hit += float(hit.sum()) * step
        wm = float(np.median(w_meas)) if w_meas else float("nan")
        dm = float(np.median(d_meas)) if d_meas else float("nan")
        print(f"{str(g['axis'][0]) + '->' :22s} {L:7.0f} {hit.mean():8.2f} "
              f"{g['width']:5.0f}->{wm:5.0f} {g['depth']:5.0f}->{dm:5.0f}")

    prec_tot = prec_hit = 0.0
    stray = []
    for da, dq, dL, dsof, db in det:
        P, step = _samples(da, dq, dL)
        hit = np.zeros(len(P), bool)
        for g in gtb:
            if abs(dsof - g["soffit_z"]) > _Z:
                continue
            a, b, L = _seg(g["axis"])
            hit |= _near(P, a, b, L, _LAT)
        prec_tot += dL
        prec_hit += float(hit.sum()) * step
        if hit.mean() < 0.5:
            stray.append((db["id"], dL, dsof))

    print(f"\nKATTAVUUS  GT-palkkien akselipituudesta mallissa: {cov_hit / max(cov_tot, 1):.3f}")
    print(f"TARKKUUS   mallin palkkipituudesta GT-palkilla   : {prec_hit / max(prec_tot, 1):.3f}")
    print(f"HARHAPALKKEJA {len(stray)}"
          + (": " + ", ".join(f"{i}({L:.0f}mm z={z:.0f})" for i, L, z in stray[:8]) if stray else ""))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

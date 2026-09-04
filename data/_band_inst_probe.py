"""Loytaako putki YLAVYOHYKKEEN seinat yhta hyvin kuin lattialla seisovat?

Rohbau-halli on yksi 10 m tila, mutta sen seinat ovat kahdessa nipussa: osa
seisoo lattialla ja osa alkaa 4-5 m korkeudelta (Facade Element / Drywall
ylhaalla). Jokainen detektori ja portti olettaa seinan ulottuvan kaistan lapi,
joten ylavyohykkeen seina on rakenteellisesti eri tapaus.

AGENTS.md kirjaa taman kumottuna (0.529 vs 0.541), mutta se mitattiin
v0.9.18:n malleilla. Sama mittaus vanhentui tanaan detektorivertailussa, joten
se ajetaan uudelleen nykyisilla malleilla.

Vyohyke luetaan INSTANSSIN omasta alareunasta suhteessa mallin lattiaan, ei
absoluuttisesta z:sta — muuten sceneen sidottu luku ei siirry.

Kaytto: _band_inst_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FACE = {5, 6, 8, 15}
MIN_PTS = 2000
MIN_FRAC = 0.30          # sama kuin _wall_inst_qa: osuus instanssin pisteista
_BAND_LO = 1000.0        # mm lattiasta — tata korkeammalta alkava on YLAVYOHYKE


def _mm(a):
    return a * 1000.0 if len(a) and float(np.ptp(a[:, 0])) < 500.0 else a


def _claimed(P, walls):
    """Onko instanssin pisteista >= MIN_FRAC jonkin mallin seinan kaistassa."""
    hit = np.zeros(len(P), bool)
    for w in walls:
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][1], float)[:2]
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = P[:, :2] - a
        t = d @ u
        off = np.abs(d @ n)
        half = 0.5 * float(w.get("thickness") or 200.0) + 150.0
        hit |= (t >= -150.0) & (t <= L + 150.0) & (off <= half)
    return hit.mean() >= MIN_FRAC


def main() -> None:
    tot = {"ala": [0, 0], "yla": [0, 0]}
    print(f"{'scene':10s} {'ALAVYOHYKE':>12s} {'YLAVYOHYKE':>12s}")
    for i in range(5):
        scene = ROOT / f"data/_rohbau/site_07/scene_0700{i}"
        mj = ROOT / f"data/output/_matrix/rohbau_0700{i}/floor_00/model.json"
        if not mj.exists():
            continue
        M = json.loads(mj.read_text(encoding="utf-8"))
        floor = min((s["elevation"] for s in M["slabs"]
                     if s["slab_type"] == "floor"), default=None)
        if floor is None:
            continue
        G = _mm(np.load(scene / "coord.npy").astype(np.float64))
        C = np.load(scene / "class.npy")
        I = np.load(scene / "instance.npy")
        got = {"ala": [0, 0], "yla": [0, 0]}
        for k in np.unique(I):
            m = I == k
            if m.sum() < MIN_PTS or not np.isin(C[m], list(FACE)).any():
                continue
            P = G[m]
            band = "yla" if (P[:, 2].min() - floor) > _BAND_LO else "ala"
            got[band][1] += 1
            if _claimed(P, M["walls"]):
                got[band][0] += 1
        for b in ("ala", "yla"):
            tot[b][0] += got[b][0]
            tot[b][1] += got[b][1]
        f = lambda p: f"{p[0]}/{p[1]} = {p[0]/p[1]:.3f}" if p[1] else "-"
        print(f"{scene.name[-5:]:10s} {f(got['ala']):>12s} {f(got['yla']):>12s}")
    print()
    for b, nimi in (("ala", "lattialla seisovat"), ("yla", "ylavyohyke")):
        p = tot[b]
        print(f"{nimi:22s} {p[0]:3d}/{p[1]:3d} = {p[0]/p[1]:.3f}" if p[1] else nimi)


if __name__ == "__main__":
    main()

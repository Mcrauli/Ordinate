"""Mikä jatkuvuussääntö kestää HARVAN skannin erottamatta palkkilinjaa väärin?

Nykyinen sääntö: sarake on tuettu jos siinä on >= 5 pistettä. Se on
absoluuttinen, joten harvalla skannilla aito seinä putoaa alle ja karsiutuu
palkkilinjana (mitattu: Rohbau hajoaa 1/250 harvennuksella).

Vertailtavat säännöt, kaikki samalla datalla ja samoilla tiheyksillä:
  abs5  sarake tuettu jos >= 5 pistettä          (nykyinen)
  abs1  sarake tuettu jos >= 1 piste             (tiheysriippumaton, herkkä kohinalle)
  rel   sarake tuettu jos >= 10 % sarakkeiden KESKIARVOSTA, vähintään 1

Erottelun on säilyttävä: AITO seinä korkealla, PALKKILINJA matalalla.
Palkkilinja tulee synteettisenä (tunnettu totuus), aidot Rohbausta.

Ajo: .venv/Scripts/python.exe data/_cont_rule_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_H, _T = 2700.0, 200.0
COL = 500.0


def beam_line_points(length=24000.0, step=50.0, bay=8000.0):
    """Palkki katon alla + pilarit 8 m välein — histogrammin tekemä valeseinä."""
    out = []
    for sgn in (1.0, -1.0):
        y = sgn * _T / 2.0
        xs = np.arange(0.0, length, step)
        zs = np.arange(_H * 0.80, _H - 30.0, step)
        X, Z = np.meshgrid(xs, zs)
        out.append(np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()]))
        zs = np.arange(60.0, _H - 60.0, step)
        for x0 in np.arange(0.0, length, bay):
            xs = np.arange(x0, min(x0 + 400.0, length), step)
            X, Z = np.meshgrid(xs, zs)
            out.append(np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()]))
    return np.vstack(out)


def face_points(length=24000.0, step=50.0):
    out = []
    for sgn in (1.0, -1.0):
        xs = np.arange(0.0, length, step)
        zs = np.arange(60.0, _H - 60.0, step)
        X, Z = np.meshgrid(xs, zs)
        out.append(np.column_stack([X.ravel(), np.full(X.size, sgn * _T / 2.0), Z.ravel()]))
    return np.vstack(out)


def continuity(counts, rule):
    if rule == "abs5":
        return float((counts >= 5).mean())
    if rule == "abs1":
        return float((counts >= 1).mean())
    if rule == "rel":
        thr = max(1.0, 0.10 * counts.mean())
        return float((counts >= thr).mean())
    raise ValueError(rule)


def col_counts(P, length, z0=0.0, h=_H):
    """Sarakkeiden pistemäärät vyötäröltä, mallin pinnan kaistasta."""
    on = np.abs(np.abs(P[:, 1]) - _T / 2.0) < 60.0
    zr = (P[on][:, 2] - z0) / h
    waist = (zr > 0.30) & (zr < 0.70)
    t = P[on][waist][:, 0]
    ncol = max(1, int(length / COL))
    ci = np.clip((t / length * ncol).astype(int), 0, ncol - 1)
    return np.bincount(ci, minlength=ncol)


def main() -> None:
    rng = np.random.default_rng(0)
    cases = [("AITO seinä", face_points()), ("PALKKILINJA", beam_line_points())]
    rules = ("abs5", "abs1", "rel")
    factors = (1, 10, 50, 100, 250, 500, 1000)

    for name, P in cases:
        print(f"\n== {name}  ({len(P):,} pistettä täydellä tiheydellä)")
        print(f"{'harvennus':>10s} {'pisteitä':>10s} " + "".join(f"{r:>8s}" for r in rules))
        order = rng.permutation(len(P))
        for f in factors:
            sub = P[order[: max(1, len(P) // f)]]
            c = col_counts(sub, 24000.0)
            vals = "".join(f"{continuity(c, r):8.2f}" for r in rules)
            print(f"1/{f:<8d} {len(sub):10,d} {vals}")

    print("\nERO (aito - palkki) — mitä isompi, sitä turvallisempi karsinta:")
    print(f"{'harvennus':>10s} " + "".join(f"{r:>8s}" for r in rules))
    for f in factors:
        row = []
        for r in rules:
            d = []
            for _, P in cases:
                o = rng.permutation(len(P))
                d.append(continuity(col_counts(P[o[: max(1, len(P) // f)]], 24000.0), r))
            row.append(d[0] - d[1])
        print(f"1/{f:<8d} " + "".join(f"{v:8.2f}" for v in row))


if __name__ == "__main__":
    main()

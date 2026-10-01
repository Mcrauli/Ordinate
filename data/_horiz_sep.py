"""Vaakapintapiirteiden erottelukyky ehdokkaissa (seina vs ei-seina)."""
import csv
import sys

import numpy as np

R = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["gtfrac"] not in ("nan", "")]
g = np.array([float(r["gtfrac"]) for r in R])
W, N = g >= 0.5, g <= 0.2
for k in ("horiz_hi", "horiz"):
    v = np.array([float(r[k]) for r in R])
    for thr in (0.2, 0.3, 0.4, 0.5, 0.7):
        print(f"{k}>{thr}: ei-seinia {(N & (v > thr)).sum()}/{N.sum()}  seinia {(W & (v > thr)).sum()}/{W.sum()}")

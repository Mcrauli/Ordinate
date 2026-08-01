"""Listaa seinat akseleittain: nakee heti onko perimetri pirstoutunut ja miten isot raot.

Aja:  .venv\\Scripts\\python data/_frag_probe.py data/output/_scale_s
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

m = json.loads(sorted(Path(sys.argv[1]).glob("floor_*/model.json"))[0]
               .read_text(encoding="utf-8"))
W = [(w["id"], np.array(w["axis"], float), w["thickness"], w["confidence"],
      w["source"]["method"]) for w in m["walls"]]

for name, ax in (("VAAKA (y=vakio)", 0), ("PYSTY (x=vakio)", 1)):
    rows = []
    for i, a, t, c, src in W:
        p0, p1 = a
        d = p1 - p0
        if abs(d[ax]) < abs(d[1 - ax]):
            continue
        rows.append((float((p0[1 - ax] + p1[1 - ax]) / 2),
                     float(min(p0[ax], p1[ax])), float(max(p0[ax], p1[ax])),
                     i, t, c, src))
    rows.sort()
    print(f"\n--- {name} ---")
    prev = None
    for cc, s0, s1, i, t, c, src in rows:
        gap = ""
        if prev is not None and abs(prev[0] - cc) < 400:
            gap = f"  <-- rako {s0 - prev[1]:.0f} mm edelliseen"
        print(f"  {i} c={cc:9.1f} {s0:9.1f}..{s1:9.1f} L={s1-s0:8.1f} "
              f"t={t:5.1f} conf={c:.2f} {src}{gap}")
        prev = (cc, s1)

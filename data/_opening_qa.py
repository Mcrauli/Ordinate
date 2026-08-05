"""Vertaa mallin aukot (ovet/ikkunat) generaattorin ovi-GT:hen.
Aja: .venv\\Scripts\\python data/_opening_qa.py <out_dir> <gt.json>"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

out_dir = Path(sys.argv[1]); gt = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
mj = sorted(out_dir.glob("floor_*/model.json")) or [out_dir / "model.json"]
m = json.loads(mj[0].read_text(encoding="utf-8"))
walls = {w["id"]: w for w in m["walls"]}

# mallin aukot maailmakeskipisteiksi (wall_id + position_along)
det = []
for o in m.get("openings", []):
    w = walls.get(o.get("wall_id"))
    if not w:
        continue
    a = np.asarray(w["axis"][0], float); b = np.asarray(w["axis"][1], float)
    L = np.linalg.norm(b - a)
    if L < 1:
        continue
    u = (b - a) / L
    wdt = float(o["width"])
    # position_along = aukon ALKUREUNA seinaa pitkin → keskus = alku + leveys/2
    ctr = a + (float(o["position_along"]) + wdt / 2.0) * u
    det.append({"center": ctr, "width": wdt, "type": o["opening_type"]})

gto = gt.get("openings", [])
print(f"mallin aukkoja: {len(det)}, GT-aukkoja: {len(gto)}")

TOL = 1500.0  # mm — keskipisteiden max etaisyys osumaksi
used = set()
hit = 0
print("\n--- KATTAVUUS (GT-aukko -> lahin malliaukko) ---")
for g in gto:
    gc = np.asarray(g["center"], float)
    best = None
    for k, d in enumerate(det):
        if k in used:
            continue
        dist = float(np.linalg.norm(d["center"] - gc))
        if best is None or dist < best[0]:
            best = (dist, k, d)
    if best and best[0] <= TOL:
        used.add(best[1]); hit += 1
        d = best[2]
        dw = d["width"] - g["width"]
        print(f"  {g['type']} ({gc[0]:.0f},{gc[1]:.0f}) w={g['width']:.0f} -> "
              f"etaisyys={best[0]:.0f}mm leveysvirhe={dw:+.0f}mm tyyppi={'OK' if d['type']==g['type'] else d['type']}")
    else:
        print(f"  {g['type']} ({gc[0]:.0f},{gc[1]:.0f}) w={g['width']:.0f} -> EI LOYTYNYT")

extra = len(det) - len(used)
print(f"\nRECALL: {hit}/{len(gto)}   yliMAARAISIA (ei GT-vastinetta): {extra}")

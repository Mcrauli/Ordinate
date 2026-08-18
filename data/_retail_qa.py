"""Vertaa liiketilamallia generaattorin ground-truthiin (_synth_retail.py .gt.json).

Kertoo kolme asiaa jotka ratkaisevat myytavyyden isossa liiketilassa:
  1. KATTAVUUS   loytyiko jokainen aito seina (ja millä lateraalivirheella)
  2. TARKKUUS    seinan akselin kohtisuora virhe + paksuusvirhe
  3. HYLLYANSA   kuinka moni malliseina istuu lattia-katto-hyllykon etupinnalla
                 (= geometria luuli hyllya seinaksi -> arkkitehti saa valeseinia)

Aja:  .venv\\Scripts\\python data/_retail_qa.py data/output/_scale_s data/_retail_s.ply.gt.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def _seg(w):
    return np.array(w["axis"][0], float), np.array(w["axis"][1], float)


def _perp_overlap(a0, a1, b0, b1):
    """(kohtisuora etaisyys mm, kulmaero deg, pituuksien limitys 0..1)."""
    u = a1 - a0
    La = np.linalg.norm(u)
    if La < 1e-6:
        return 1e9, 90.0, 0.0
    u = u / La
    v = b1 - b0
    Lb = np.linalg.norm(v)
    if Lb < 1e-6:
        return 1e9, 90.0, 0.0
    v = v / Lb
    ang = np.degrees(np.arccos(min(1.0, abs(float(u @ v)))))
    n = np.array([-u[1], u[0]])
    d = abs(float((b0 - a0) @ n)) * 0.5 + abs(float((b1 - a0) @ n)) * 0.5
    s = np.array([(b0 - a0) @ u, (b1 - a0) @ u])
    lo, hi = max(0.0, s.min()), min(La, s.max())
    return d, ang, max(0.0, hi - lo) / La


def main() -> None:
    out_dir = Path(sys.argv[1])
    gt = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    # Yksitiedostoajo kirjoittaa model.json:n juureen, monikerros floor_NN:aan.
    mj = sorted(out_dir.glob("floor_*/model.json")) or (
        [out_dir / "model.json"] if (out_dir / "model.json").exists() else [])
    if not mj:
        print(f"ei model.json:ia hakemistossa {out_dir}")
        return
    model = json.loads(mj[0].read_text(encoding="utf-8"))
    walls = model["walls"]

    print(f"malli: {len(walls)} seinaa, GT: {len(gt['walls'])} seinaa, "
          f"{len(gt['columns'])} pilaria")

    used = set()
    print("\n--- KATTAVUUS (GT-seina -> lahin malliseina) ---")
    hit = 0
    for i, g in enumerate(gt["walls"]):
        g0, g1 = _seg(g)
        best = None
        for j, w in enumerate(walls):
            w0, w1 = _seg(w)
            d, ang, ov = _perp_overlap(g0, g1, w0, w1)
            if ang > 8.0 or ov < 0.25:
                continue
            if best is None or d < best[0]:
                best = (d, ang, ov, j, w)
        L = np.linalg.norm(g1 - g0)
        if best is None or best[0] > 600.0:
            print(f"  GT{i:02d} L={L/1000:5.1f} m t={g['thickness']:.0f}  EI LOYTYNYT")
            continue
        d, ang, ov, j, w = best
        used.add(j)
        hit += 1
        dt = w["thickness"] - g["thickness"]
        mt = w.get("measured_thickness")
        print(f"  GT{i:02d} L={L/1000:5.1f} m t={g['thickness']:.0f}  -> {w['id']} "
              f"lat={d:6.1f} mm  kulma={ang:4.1f}  kate={ov:4.2f}  "
              f"dt={dt:+6.1f} (mit={mt if mt is None else round(mt,1)})")
    print(f"  loytyi {hit}/{len(gt['walls'])}")

    shelves = [(np.array(a, float), np.array(b, float)) for a, b in gt.get("shelf_faces", [])]
    print("\n--- YLIMAARAISET (ei GT-vastinetta) ---")
    n_shelf = n_other = 0
    for j, w in enumerate(walls):
        if j in used:
            continue
        w0, w1 = _seg(w)
        L = np.linalg.norm(w1 - w0)
        tag = ""
        for s0, s1 in shelves:
            d, ang, ov = _perp_overlap(s0, s1, w0, w1)
            if ang < 8.0 and ov > 0.15 and d < 700.0:
                tag = f"HYLLY (d={d:.0f} mm)"
                break
        if tag:
            n_shelf += 1
        else:
            n_other += 1
        if L > 1500.0:
            print(f"  {w['id']} L={L/1000:5.1f} m t={w['thickness']:.0f} "
                  f"conf={w['confidence']:.2f} {tag}")
    print(f"  hyllysta tehtyja seinia: {n_shelf}   muita ylimaaraisia: {n_other}")

    sp = model.get("spaces", [])
    tot = 0.0
    for s in sp:
        b = np.array(s["boundary"], float)
        if len(b) >= 3:
            x, y = b[:, 0], b[:, 1]
            tot += abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2
    sx, sy, _h = gt["size"]
    print(f"\n--- TILAT --- {len(sp)} kpl, yhteensa {tot/1e6:.0f} m2 "
          f"(hallin sisamitta {sx*sy/1e6:.0f} m2)")
    print(f"--- PILARIT --- malli {len(model.get('columns', []))}, GT {len(gt['columns'])}")


if __name__ == "__main__":
    main()

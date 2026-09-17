"""Aukkojen SIJOITUSTARKKUUS tunnettua totuutta vasten.

Aukkoja on mitattu tähän asti vain löytymisenä (osuuko mallin aukko GT-aukon
lähelle). Sitä ei ole mitattu kertaakaan, kuinka monta senttiä väärässä ovi
on, onko leveys oikein tai onko ikkunan alareuna oikealla korkeudella — ja
arkkitehdille juuri ne ovat mallin laatu.

Totuus: keilattu synteettinen myymälä (`data/_synth_store.py`), jonka
`gt.json` kertoo jokaisen aukon keskipisteen, leveyden, korkeuden,
alareunan ja tyypin millin tarkkuudella.

Käyttö: _opening_place_qa.py <model.json> <gt.json>
"""
from __future__ import annotations

import json
import sys

import numpy as np

_MATCH = 1500.0     # mm — GT- ja mallin aukon keskipisteiden max etäisyys


def _model_openings(m: dict) -> list[dict]:
    walls = {w["id"]: w for w in m["walls"]}
    floor = min((s["elevation"] for s in m.get("slabs", []) if s.get("slab_type") == "floor"),
                default=0.0)
    out = []
    for o in m.get("openings", []):
        w = walls.get(o["wall_id"])
        if w is None:
            continue
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        c = a + u * (o["position_along"] + o["width"] / 2.0)
        out.append(dict(center=c, u=u, width=o["width"], height=o["opening_height"],
                        sill=o["sill_height"], type=o["opening_type"], id=o["id"],
                        z0=float(w.get("z_min", floor))))
    return out


def main(model_json: str, gt_json: str) -> None:
    m = json.load(open(model_json, encoding="utf-8"))
    g = json.load(open(gt_json, encoding="utf-8"))
    gt = g["openings"]
    mo = _model_openings(m)
    used: set[int] = set()
    rows = []
    for gi, go in enumerate(gt):
        gc = np.array(go["center"], float)
        best, bd = None, _MATCH
        for mi, o in enumerate(mo):
            if mi in used:
                continue
            d = float(np.linalg.norm(o["center"] - gc))
            if d < bd:
                best, bd = mi, d
        if best is None:
            rows.append((gi, go, None))
            continue
        used.add(best)
        rows.append((gi, go, mo[best]))

    found = [r for r in rows if r[2] is not None]
    print(f"GT-aukkoja {len(gt)} | löytyi {len(found)} | mallin aukkoja {len(mo)} "
          f"| vääriä {len(mo) - len(found)}")
    print(f"{'GT':>3} {'tyyppi':7} {'malli':7} {'keskip. ero':>11} {'pituussuunta':>12} "
          f"{'leveys GT/malli':>16} {'korkeus GT/malli':>17} {'alareuna GT/malli':>18}")
    along_err, w_err, h_err, s_err, type_ok = [], [], [], [], 0
    for gi, go, o in rows:
        if o is None:
            print(f"{gi:3d} {go['type']:7s} {'—':7s} {'ei löytynyt':>11}  "
                  f"(leveys {go['width']:.0f}, korkeus {go['height']:.0f}, alareuna {go['sill']:.0f})")
            continue
        gc = np.array(go["center"], float)
        d = o["center"] - gc
        along = float(d @ o["u"])
        along_err.append(abs(along)); w_err.append(o["width"] - go["width"])
        h_err.append(o["height"] - go["height"]); s_err.append(o["sill"] - go["sill"])
        type_ok += o["type"] == go["type"]
        print(f"{gi:3d} {go['type']:7s} {o['type']:7s} {np.linalg.norm(d):9.0f} mm {along:+10.0f} mm "
              f"{go['width']:7.0f}/{o['width']:<7.0f} {go['height']:8.0f}/{o['height']:<7.0f} "
              f"{go['sill']:9.0f}/{o['sill']:<7.0f}")
    if found:
        med = lambda x: float(np.median(np.abs(x)))
        print(f"\nmediaanivirhe: pituussuunta {med(along_err):.0f} mm | leveys {med(w_err):.0f} mm "
              f"| korkeus {med(h_err):.0f} mm | alareuna {med(s_err):.0f} mm "
              f"| tyyppi oikein {type_ok}/{len(found)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

"""Kuroako mittarin katkaisu umpeen sen ERON GT:hen jonka se itse myontaa?

`coverage.wallish_points` vaatii XY-solulta `0.50 * kaista` pystypintaa ennen
kuin se laskee solun seinaksi. Se on SAMA taso-eika-suhde-vika joka loytyi jo
`wall_histogram`ista ja `wall_normals`ista, nyt kolmannessa paikassa: 10 m
hallissa vaatimus on 4.6 m, joten 3 m valiseina ei ole mittarille seina.

Mitattu (`data/_metric_blindness.py`): kun TAYDELLISEEN GT-malliin lisataan
kaikki alle 4 m seinat — 77-83 % kaikista seinista — kattavuus nousee 0.014,
0.020 ja 0.022, ja F1 LASKEE. Mittari siis rankaisee oikeiden seinien
loytamisesta.

Mittaria ei saa muuttaa mieltymyksen perusteella. Sille on riippumaton
tuomari: coverage.py:n oma dokumentaatio myontaa etta mittari eroaa GT:sta
pahiten kahdella scenella (07003: 0.597 vs 0.849, 07004: 0.640 vs 0.759) —
ja juuri niissa on eniten lyhyita seinia. Jos katkaisu kuroo NAMA umpeen
rikkomatta kolmea muuta, muutos on GT:n vahvistama.

Ajetaan valmiisiin malleihin (data/output/_matrix/*), joten detektori ei
muutu — vain mittari.

Kaytto: _metric_cap_probe.py [katkaisu_mm ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_GT = {"rohbau_07000": 0.920, "rohbau_07001": 0.905, "rohbau_07002": 0.863,
       "rohbau_07003": 0.849, "rohbau_07004": 0.759}


def _model_walls(path: Path):
    from ordinate.schemas.model import ElementSource, Wall
    m = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for w in m["walls"]:
        out.append(Wall(id=w["id"], confidence=w.get("confidence", 1.0),
                        classification=w.get("classification", "wall"),
                        source=ElementSource(method="manual"),
                        axis=w["axis"], height=w.get("height", 3000.0),
                        thickness=w.get("thickness", 200.0),
                        z_min=w.get("z_min", 0.0)))
    return out


def main(*caps: str) -> None:
    import open3d as o3d

    from ordinate.core.qa import coverage as CV

    cap_list = [float(c) for c in caps] or [2000.0, 2400.0, 2800.0, 3400.0]
    orig = CV._SPAN_FRAC

    rows: dict[str, dict] = {}
    for name, gt in _GT.items():
        model = ROOT / "data/output/_matrix" / name / "floor_00/model.json"
        cloud = ROOT / f"data/_rohbau/site_07/scene_{name.split('_')[1]}/cloud.ply"
        if not model.exists() or not cloud.exists():
            print(f"{name}: puuttuu")
            continue
        walls = _model_walls(model)
        pts = np.asarray(o3d.io.read_point_cloud(str(cloud)).points)
        if np.ptp(pts[:, 0]) < 500.0:    # metrit -> mm, sama saanto kuin loaderissa
            pts = pts * 1000.0
        floor = float(np.percentile(pts[:, 2], 2))
        ceiling = float(np.percentile(pts[:, 2], 98))
        band = (ceiling - 300.0) - (floor + 400.0)
        rows[name] = {"gt": gt, "band": band}

        cov, _ = CV.wall_scores(pts, walls, floor, ceiling)
        rows[name]["nyky"] = cov
        for cap in cap_list:
            # Katkaisu ilmaistaan osuutena, koska `wallish_points` ottaa
            # vastaan vain `_SPAN_FRAC`in — sama luku, eri esitys.
            CV._SPAN_FRAC = min(orig, cap / band)
            try:
                c, _ = CV.wall_scores(pts, walls, floor, ceiling)
            finally:
                CV._SPAN_FRAC = orig
            rows[name][f"{cap:.0f}"] = c
        print(f"{name}: mitattu (kaista {band:.0f} mm)", flush=True)

    cols = ["nyky"] + [f"{c:.0f}" for c in cap_list]
    print(f"\n{'scene':14s} {'GT':>7s} {'nyky':>7s} "
          + " ".join(f"{c:>7s}" for c in cols[1:]))
    for name, r in rows.items():
        print(f"{name:14s} {r['gt']:7.3f} "
              + " ".join(f"{r[c]:7.3f}" for c in cols))
    print(f"\n{'ERO GT:hen':14s} {'':>7s} "
          + " ".join(f"{c:>7s}" for c in cols))
    for name, r in rows.items():
        print(f"{name:14s} {'':>7s} "
              + " ".join(f"{r[c]-r['gt']:+7.3f}" for c in cols))
    print(f"\n{'KESKIVIRHE':14s} {'':>7s} "
          + " ".join(f"{np.mean([abs(r[c]-r['gt']) for r in rows.values()]):7.3f}"
                     for c in cols))


if __name__ == "__main__":
    main(*sys.argv[1:])

"""Sama julkisivuruudukko + totuus ROHBAUSTA — siirtyyko synteettinen malli?

Synteettisella opittu ja synteettisella validoitu malli ei todista mitaan
oikeasta keilauksesta. Rohbau3D:ssa aukot ovat per-piste-luokkina
(7 Wall Cutout, 12 Window Cutout, 13 Window, 14 Door Rough Opening), joten
sama ruudukko ja sama totuusmaski saadaan sielta ilman gt.jsonia.

Seinat otetaan TUOTANNON mallista, koska Rohbaussa ei ole GT-seinia — eli
malli arvioidaan taysin samalla syotteella kuin tuotanto nakee.

Kaytto: _op_rohbau.py <model.json> <scene_dir> <out_dir> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scan2bim.core.segmentation import opening_detector as OD  # noqa: E402
from scan2bim.schemas.model import ElementSource, Wall  # noqa: E402

OPEN_CLS = (7, 12, 13, 14)
_cap: list[dict] = []


def _capture(occ, col_pts, xe, ze, n_x, n_z, length, wall, floor_z, start_idx,
             start_anchor, end_anchor):
    _cap.append({"occ": np.asarray(occ), "col": np.asarray(col_pts),
                 "xe": np.asarray(xe), "ze": np.asarray(ze),
                 "anchors": (bool(start_anchor), bool(end_anchor)),
                 "length": float(length)})
    return []


def main(model_json: str, scene: str, out: str, tag: str = "") -> None:
    d = Path(scene)
    G = np.load(d / "coord.npy").astype(np.float64)
    if float(np.ptp(G[:, 0])) < 500.0:
        G = G * 1000.0
    C = np.load(d / "class.npy")
    walls_raw = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    name = tag or d.name
    outp = Path(out)
    outp.mkdir(parents=True, exist_ok=True)

    OD._find_openings = _capture
    floor_z = min((float(w["z_min"]) for w in walls_raw), default=0.0)
    walls = [Wall(id=w["id"], confidence=1.0, classification="wall",
                  source=ElementSource(method="manual"),
                  axis=[[float(w["axis"][0][0]), float(w["axis"][0][1])],
                        [float(w["axis"][-1][0]), float(w["axis"][-1][1])]],
                  height=float(w["height"]), thickness=float(w["thickness"] or 200.0),
                  z_min=float(w["z_min"])) for w in walls_raw]
    is_open = np.isin(C, OPEN_CLS)
    saved = 0
    for w in walls:
        _cap.clear()
        OD._wall_openings(w, G, floor_z, 0, walls, None)
        if not _cap:
            continue
        c = _cap[0]
        a = np.asarray(w.axis[0], float)
        b = np.asarray(w.axis[1], float)
        L = float(np.linalg.norm(b - a))
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        rel = G[:, :2] - a
        t, perp = rel @ u, rel @ n
        m = is_open & (np.abs(perp) < w.thickness / 2.0 + 150.0) & (t > 0) & (t < L)
        lab = np.zeros((len(c["xe"]) - 1, len(c["ze"]) - 1), np.uint8)
        if int(m.sum()) > 50:
            h, _, _ = np.histogram2d(t[m], G[m][:, 2], bins=[c["xe"], c["ze"]])
            lab = (h > 0).astype(np.uint8)
        np.savez_compressed(
            outp / f"rohbau{name[-6:]}_{w.id}.npz",
            occ=c["occ"].astype(np.uint8), col=c["col"].astype(np.float32),
            xe=c["xe"], ze=c["ze"], lab=lab,
            anchors=np.array(c["anchors"], bool),
            meta=np.array([c["length"], w.thickness, w.z_min, w.height], float))
        saved += 1
    print(f"{name}: {saved} seinaa -> {outp}")


if __name__ == "__main__":
    main(*sys.argv[1:])

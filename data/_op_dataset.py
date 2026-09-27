"""Aukkodetektion opetusdata: seinan julkisivuruudukko + totuus.

`opening_detector._wall_openings` rakentaa jokaiselle seinalle miehitys-
ruudukon (n_x x n_z) ja etsii siita aukkoja kasin kirjoitetuilla saannoilla.
Ruudukko ON kuva, ja siihen on nyt saatavilla tasmallinen totuus: keilattu
synteettinen myymala tietaa jokaisen aukon paikan, leveyden, sillin ja
ylareunan.

Tama poimii saman ruudukon jota TUOTANTO kayttaa — ei kopiota siita — ja
kirjoittaa sen levylle totuusmaskin kanssa. Ruudukko otetaan patchaamalla
`_find_openings`, jolloin esikasittely (pinnanvalinta, tiheystasoitus,
kynnys) on bitilleen sama kuin ajossa.

Kaytto: _op_dataset.py <skenehakemisto> [lisaa...] --out data/_op_data
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ordinate.core.segmentation import opening_detector as OD  # noqa: E402
from ordinate.schemas.model import ElementSource, Wall  # noqa: E402

_captured: list[dict] = []


def _capture(occ, col_pts, xe, ze, n_x, n_z, length, wall, floor_z, start_idx,
             start_anchor, end_anchor):
    _captured.append({"occ": np.asarray(occ), "col_pts": np.asarray(col_pts),
                      "xe": np.asarray(xe), "ze": np.asarray(ze),
                      "wall_id": wall.id, "length": float(length),
                      "anchors": (bool(start_anchor), bool(end_anchor))})
    return []


def _walls_from_gt(g: dict) -> list[Wall]:
    z0 = float(g["floor_z"])
    h = float(g["ceiling_z"]) - z0
    out = []
    for i, w in enumerate(g["walls"]):
        a, b = w["axis"][0], w["axis"][1]
        out.append(Wall(id=f"gt_{i:03d}", confidence=1.0, classification="wall",
                        source=ElementSource(method="manual"),
                        axis=[[float(a[0]), float(a[1])], [float(b[0]), float(b[1])]],
                        height=h, thickness=float(w["thickness"]), z_min=z0))
    return out


def _label(wall: Wall, g: dict, xe: np.ndarray, ze: np.ndarray) -> np.ndarray:
    """Totuusmaski ruudukon muodossa: 1 = aukkoa."""
    a = np.asarray(wall.axis[0], float)
    b = np.asarray(wall.axis[1], float)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    m = np.zeros((len(xe) - 1, len(ze) - 1), np.uint8)
    xc = 0.5 * (xe[:-1] + xe[1:])
    zc = 0.5 * (ze[:-1] + ze[1:])
    for op in g["openings"]:
        c = np.asarray(op["center"], float)
        d = c - a
        if abs(float(d @ n)) > 400.0:
            continue
        t = float(d @ u)
        if not (-200.0 <= t <= L + 200.0):
            continue
        sill = float(op.get("sill", 0.0))
        head = sill + float(op["height"])
        half = 0.5 * float(op["width"])
        cols = np.abs(xc - t) <= half
        rows = (zc >= float(g["floor_z"]) + sill) & (zc <= float(g["floor_z"]) + head)
        m[np.ix_(cols, rows)] = 1
    return m


def main() -> None:
    args = sys.argv[1:]
    out = Path("data/_op_data")
    if "--out" in args:
        i = args.index("--out")
        out = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    out.mkdir(parents=True, exist_ok=True)

    OD._find_openings = _capture
    n_saved = 0
    for sd in args:
        d = Path(sd)
        g = json.loads((d / "gt.json").read_text(encoding="utf-8"))
        P = np.load(d / "coord.npy").astype(np.float64)
        walls = _walls_from_gt(g)
        floor_z = float(g["floor_z"])
        print(f"{d.name}: {len(P):,} pistetta, {len(walls)} seinaa", flush=True)
        for w in walls:
            _captured.clear()
            OD._wall_openings(w, P, floor_z, 0, walls, None)
            if not _captured:
                continue
            c = _captured[0]
            lab = _label(w, g, c["xe"], c["ze"])
            np.savez_compressed(
                out / f"{d.name}_{w.id}.npz",
                occ=c["occ"].astype(np.uint8), col=c["col_pts"].astype(np.float32),
                xe=c["xe"], ze=c["ze"], lab=lab,
                anchors=np.array(c["anchors"], bool),
                meta=np.array([c["length"], w.thickness, w.z_min, w.height], float))
            n_saved += 1
        del P
    print(f"tallennettu {n_saved} seinaa -> {out}")


if __name__ == "__main__":
    main()

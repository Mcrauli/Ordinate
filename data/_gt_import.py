"""Labeloidut luokkatiedostot -> coord.npy + class.npy (Rohbau-numerointi).

CloudComparessa segmentoidut luokat tulevat ulos omina tiedostoinaan. Tama
lukee ne, yhdistaa ja kirjoittaa saman muodon jota Rohbau3D kayttaa, jotta
`_rohbau_qa.py`, `_wall_inst_qa.py`, `_opening_qa.py` ja `_gap_probe.py`
toimivat kellarilla ilman muutoksia.

Numerointi on Rohbaun rekisteri (ks. `_rohbau_qa._REG`):
  1 Ceiling  4 Floor  5 Wall  6 Drywall  9 Beam  10 Column  17 TGA  0 None
`_rohbau_qa` laskee seinaksi luokat Wall/Drywall/Parapet/Facade, joten
kevytrakenteinen valiseina kannattaa merkita drywall.ply:ksi ja betoniseina
wall.ply:ksi — tai kaikki wall.ply:ksi jos ero ei kiinnosta.

Tiedostonimi -> luokka:
  wall 5 | drywall 6 | floor 4 | ceiling 1 | beam 9 | column 10
  pipe/tga 17 | door 14 | window 13 | other/none 0

Kaytto: _gt_import.py <hakemisto>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_CLASS = {
    "wall": 5, "drywall": 6, "floor": 4, "ceiling": 1, "beam": 9,
    "column": 10, "pipe": 17, "tga": 17, "door": 14, "window": 13,
    "other": 0, "none": 0,
}


def main(folder: str) -> None:
    import open3d as o3d
    d = Path(folder)
    coords, classes = [], []
    for f in sorted(d.glob("*.ply")):
        name = f.stem.lower().split("_")[0]
        if name not in _CLASS:
            print(f"  ohitettu {f.name} (tuntematon luokka)")
            continue
        pts = np.asarray(o3d.io.read_point_cloud(str(f)).points)
        if not len(pts):
            continue
        coords.append(pts)
        classes.append(np.full(len(pts), _CLASS[name], dtype=np.int16))
        print(f"  {f.name:16s} {_CLASS[name]:3d}  {len(pts):9,d} pistetta")
    if not coords:
        raise SystemExit("ei luokkatiedostoja — nimea ne wall.ply, floor.ply, ...")
    P = np.vstack(coords)
    C = np.concatenate(classes)
    np.save(d / "coord.npy", P.astype(np.float32))
    np.save(d / "class.npy", C)
    print(f"yhteensa {len(P):,} pistetta -> {d/'coord.npy'}, {d/'class.npy'}")


if __name__ == "__main__":
    main(*sys.argv[1:])

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

YKSIKKO: labelointi voi tulla joko putken viemasta pilvesta (mm) tai suoraan
CloudComparessa avatusta E57:sta (metrit) — kumpikin nayttaa CC:ssa
identtiselta. Ilman muunnosta metreissa labeloitu GT on 1000x pielessa ja
jokainen mittari palauttaa nollan ILMAN virheilmoitusta. Yksikko luetaan
`loader.metre_scale`:lla, samasta paikasta kuin pilvelle — sama juurisyy kuin
`scanner_origins`issa, jossa oma erillinen sääntö oli vaarassa.

Kaytto: _gt_import.py <hakemisto>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scan2bim.core.geometry.loader import metre_scale  # noqa: E402

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
    scale = metre_scale(P)
    if scale != 1.0:
        print(f"pilvi on METREISSA -> skaalataan x{scale:.0f} millimetreiksi")
        P = P * scale
    np.save(d / "coord.npy", P.astype(np.float32))
    np.save(d / "class.npy", C)
    print(f"yhteensa {len(P):,} pistetta -> {d/'coord.npy'}, {d/'class.npy'}")
    lo, hi = P.min(axis=0), P.max(axis=0)
    print(f"laajuus {(hi[0]-lo[0])/1000:.1f} x {(hi[1]-lo[1])/1000:.1f} x "
          f"{(hi[2]-lo[2])/1000:.1f} m")
    print(f"sijainti x {lo[0]/1000:.0f}..{hi[0]/1000:.0f} m, "
          f"y {lo[1]/1000:.0f}..{hi[1]/1000:.0f} m  "
          f"— TARKISTA etta tama osuu mallin alueelle; CloudCompare voi "
          f"tarjota koordinaattien siirtoa (global shift) latauksessa ja "
          f"tallennuksessa, ja siirretty GT ei osu mihinkaan.")


if __name__ == "__main__":
    main(*sys.argv[1:])

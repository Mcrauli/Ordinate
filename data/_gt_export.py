"""Vie yksi keilausasema labeloitavaksi CloudComparessa.

Kellarilla ei ole ground truthia, ja ilman sita jokainen sailyta/poista-paatos
on arvaus. Rohbau3D:lla on per-piste-GT ja siella kaikki mittarit toimivat;
tama tekee kellarista saman.

Vienti harventaa aseman ~4 M pisteeseen, koska CloudComparen segmentointi
kaymataan hitaaksi isommalla eika seinan rajaa tarvitse osoittaa millilleen —
luokka luetaan pisteen sijainnista, ei sen tarkkuudesta.

TYONKULKU
  1. _gt_export.py <asema.e57> data/_gt/kellari_020.ply
  2. Avaa PLY CloudComparessa.
  3. Segmentoi luokka kerrallaan (Segment-tyokalu, "Segment In"):
     tallenna jokainen luokka omaksi tiedostoksi samaan hakemistoon nimella
     wall.ply, floor.ply, ceiling.ply, column.ply, pipe.ply, other.ply.
     Kaikkia ei tarvitse: labeloimatta jaanyt piste ei osallistu mittaukseen.
  4. _gt_import.py data/_gt/kellari_020  -> coord.npy + class.npy
  5. Mittaa: _rohbau_qa.py <model.json> coord.npy class.npy

Kaytto: _gt_export.py <pilvi.e57|ply> <ulos.ply> [max_pts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scan2bim.core.geometry.loader import load_point_cloud  # noqa: E402


def main(src: str, out: str, max_pts: str = "4000000") -> None:
    import open3d as o3d
    cloud = load_point_cloud(Path(src), e57_colors=True)
    pts = np.asarray(cloud.points)
    lim = int(max_pts)
    step = max(1, -(-len(pts) // lim))
    pts = np.ascontiguousarray(pts[::step])
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    if cloud.has_colors():
        pc.colors = o3d.utility.Vector3dVector(
            np.asarray(cloud.colors)[::step])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_point_cloud(str(out), pc)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    print(f"{len(pts):,} pistetta (1/{step})  -> {out}")
    print(f"laajuus {(hi[0]-lo[0])/1000:.1f} x {(hi[1]-lo[1])/1000:.1f} x "
          f"{(hi[2]-lo[2])/1000:.1f} m")


if __name__ == "__main__":
    main(*sys.argv[1:])

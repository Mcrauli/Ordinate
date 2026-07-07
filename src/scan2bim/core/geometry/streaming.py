"""Muistitehokas lataus useista tiedostoista: yksi kerrallaan, Z-kaista suodatetaan heti."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import open3d as o3d


def load_floor_slice(
    paths: list[Path],
    z_lo: float,
    z_hi: float,
    voxel_size: float = 1.0,
    progress_cb=None,
    icp_refine: bool = False,
    sample_out: list | None = None,
) -> o3d.geometry.PointCloud:
    """
    Lataa vain Z-kaistan [z_lo, z_hi] kaikista tiedostoista.
    Huippumuisti = yhden tiedoston koko (ei kaikkien summa).

    icp_refine=True: kukin siivu kohdistetaan kasvavaan referenssiin ICP:llä,
    jotta karkeasta E57-posesta tulevat kahdentumat poistuvat.

    sample_out: jos annettu, siihen lisätään (tiedostonimi, karkea 100mm-otos)
    per tiedosto — skannien keskinäisen yhteensopivuuden tarkistukseen.
    """
    from scan2bim.core.geometry.loader import (
        load_point_cloud, read_ply_xyz_band, ply_autoscale_factor,
    )

    merged = o3d.geometry.PointCloud()
    ref: o3d.geometry.PointCloud | None = None  # kevyt referenssi ICP:lle
    for i, path in enumerate(paths):
        if progress_cb:
            progress_cb(f"  [{i+1}/{len(paths)}] {path.name}")

        # Binääri-PLY luetaan LOHKOISSA Z-kaista suoraan suodattaen — iso skanni
        # (satoja M pisteitä) ei mahdu muistiin kokonaan. Muut formaatit / ascii-
        # PLY: koko tiedosto (E57 lukee jo skanneittain, muut ovat pienempiä).
        band: np.ndarray | None = None
        if path.suffix.lower() == ".ply":
            try:
                scale = ply_autoscale_factor(path)
                raw = read_ply_xyz_band(path, z_lo / scale, z_hi / scale)
                if raw is not None:
                    band = raw * scale if scale != 1.0 else raw
            except Exception as e:
                if progress_cb:
                    progress_cb(f"  VAROITUS: {path.name} kaistaluku epäonnistui — {e}")
                band = None

        if band is not None:
            if len(band) < 50:
                continue
            slice_cloud = o3d.geometry.PointCloud()
            slice_cloud.points = o3d.utility.Vector3dVector(band)
        else:
            try:
                cloud = load_point_cloud(path)
            except Exception as e:
                if progress_cb:
                    progress_cb(f"  VAROITUS: {path.name} ohitettiin — {e}")
                continue

            # Vapauta normaalit ja värit heti — tarvitaan vain XYZ. Säästää ~1.3 GB/tiedosto.
            cloud.normals = o3d.utility.Vector3dVector()
            cloud.colors = o3d.utility.Vector3dVector()

            pts = np.asarray(cloud.points)
            mask = (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
            n = int(mask.sum())
            if n < 50:
                del cloud
                continue

            idx = np.where(mask)[0]
            slice_cloud = cloud.select_by_index(idx)
            del cloud  # vapauta muisti ennen downsamplausta

        if voxel_size > 0.0:
            slice_cloud = slice_cloud.voxel_down_sample(voxel_size)

        if icp_refine:
            from scan2bim.core.geometry.registration import align_to_reference
            if ref is not None:
                slice_cloud = align_to_reference(slice_cloud, ref)
            # päivitä kevyt referenssi (rajaa koko ICP:n nopeuttamiseksi)
            merged += slice_cloud
            ref = merged.voxel_down_sample(max(voxel_size * 8.0, 20.0))
        else:
            merged += slice_cloud

        if sample_out is not None:
            coarse = slice_cloud.voxel_down_sample(100.0)
            sample_out.append((path.name, np.asarray(coarse.points).copy()))

    return merged


def check_scan_consistency(samples: list, dist_thr: float = 120.0) -> list[str]:
    """Palauttaa tiedostot jotka eivät jaa pintoja muiden skannien kanssa.

    Saman tilan skannit limittyvät: ison osan pisteistä on löydettävä
    vastinpiste muista skanneista. Eri kohteen skanni samassa koordinaatistossa
    risteää satunnaisesti → mediaanietäisyys muihin on suuri → varoitus.
    Mitattu: saman talon skannit medNN 6–37 mm (100 mm otoksella), kymmenen
    ERI asunnon setti 143–2720 mm → 120 mm erottaa täydellä marginaalilla."""
    if len(samples) < 2:
        return []
    from scipy.spatial import cKDTree
    suspicious: list[str] = []
    for i, (name, pts) in enumerate(samples):
        if len(pts) < 50:
            continue
        others = np.vstack([p for j, (_, p) in enumerate(samples) if j != i and len(p)])
        if len(others) < 50:
            continue
        tree = cKDTree(others)
        d, _ = tree.query(pts, k=1)
        if float(np.median(d)) > dist_thr:
            suspicious.append(name)
    return suspicious

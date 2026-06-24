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
) -> o3d.geometry.PointCloud:
    """
    Lataa vain Z-kaistan [z_lo, z_hi] kaikista tiedostoista.
    Huippumuisti = yhden tiedoston koko (ei kaikkien summa).

    icp_refine=True: kukin siivu kohdistetaan kasvavaan referenssiin ICP:llä,
    jotta karkeasta E57-posesta tulevat kahdentumat poistuvat.
    """
    from scan2bim.core.geometry.loader import load_point_cloud

    merged = o3d.geometry.PointCloud()
    ref: o3d.geometry.PointCloud | None = None  # kevyt referenssi ICP:lle
    for i, path in enumerate(paths):
        if progress_cb:
            progress_cb(f"  [{i+1}/{len(paths)}] {path.name}")
        try:
            cloud = load_point_cloud(path)
        except Exception:
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

    return merged

"""MUISTIPIIKIN ERITTELY: mika VARAA muistin semanttisen suodattimen kohdalla.

_scale_run kertoo ETTA piikki on siina vaiheessa (10.8 GB). Se ei kerro mika
osuus on kolme yhtaaikaista pilvea ja mika on suodattimen oma tyoskentelysetti.
Tama toistaa saman tilanteen ilman koko putkea ja tulostaa RSS:n joka askeleen
jalkeen + pistemaarat, seka _classify:n sisalta askelkohtaisen jaljen.

Aja:  .venv\\Scripts\\python data/_mem_probe.py data/_retail_l.ply
"""
from __future__ import annotations

import argparse
import gc
import threading
import time
from pathlib import Path

import numpy as np
import psutil

_PROC = psutil.Process()
_T0 = time.time()
_PEAK = [0.0]
_STEP_PEAK = [0.0]


def _watch() -> None:
    """Askelten VALISSA syntyvat transientit eivat nay jalkikateen luetusta
    RSS:sta — iso lataus voi kayda 3 GB:ssa ja palata 0.2 GB:hen."""
    while True:
        g = _PROC.memory_info().rss / 1e9
        _PEAK[0] = max(_PEAK[0], g)
        _STEP_PEAK[0] = max(_STEP_PEAK[0], g)
        time.sleep(0.2)


def rss(tag: str) -> float:
    gc.collect()
    g = _PROC.memory_info().rss / 1e9
    _PEAK[0] = max(_PEAK[0], g)
    top = max(_STEP_PEAK[0], g)
    _STEP_PEAK[0] = 0.0
    print(f"[{time.time()-_T0:6.1f}s] RSS {g:6.2f} GB (askelhuippu {top:5.2f}) {tag}",
          flush=True)
    return g


def _trace_classify(filt, pts_full):
    """Suodattimen esityo askel kerrallaan, TODELLISILLA funktioilla.

    Askelhuippu (0.2 s naytteistys) on tassa se olennainen luku: iso osa
    kulutuksesta on transienttia joka ei nay askeleen jalkeisessa RSS:ssa."""
    from ordinate.core.segmentation import pointnet_filter as pnf

    rss(f"  classify sisaan, pts_full {len(pts_full):,}")
    origin = pts_full.min(axis=0)
    vkey = pnf._voxel_keys(pts_full, origin)
    rss(f"  + vkey {vkey.nbytes/1e9:.2f} GB")
    vuniq, first, inv = np.unique(vkey, return_index=True, return_inverse=True)
    del vkey
    rss(f"  + unique -> {len(first):,} voxelia, inv {inv.nbytes/1e9:.2f} GB")
    wpts = pts_full[first]
    del first
    rss("  + wpts")

    from ordinate.core.segmentation import point_features as pf
    h = pf.height(wpts)
    rss("  + height")
    g = pf.geometric(wpts)
    rss("  + geometric")
    c = pf.column(wpts)
    rss("  + column")
    scene_extra = np.column_stack([h, g, c]).astype(np.float32)
    del h, g, c
    rss(f"  + scene_extra {scene_extra.nbytes/1e9:.2f} GB")

    votes = np.zeros((len(wpts), pnf._N_CLASSES), dtype=np.float32)
    rss(f"  + votes {votes.nbytes/1e9:.2f} GB")
    del votes, scene_extra, vuniq, inv, wpts
    gc.collect()
    rss("  (vapautettu)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cloud")
    ap.add_argument("--skip-filter", action="store_true")
    ap.add_argument("--real", action="store_true",
                    help="aja oikea filter_with_labels (huippu), ei askeljalkea")
    a = ap.parse_args()
    paths = [Path(a.cloud)]
    threading.Thread(target=_watch, daemon=True).start()

    from ordinate.core.geometry.floor_splitter import detect_floors_from_files
    from ordinate.core.geometry.loader import (
        load_point_cloud as _lpc, ply_z_range, ply_autoscale_factor)
    from ordinate.core.geometry.streaming import load_floor_slice as _lfs
    from ordinate.core.pipeline import _auto_voxel

    rss("alku")
    floors = detect_floors_from_files(paths, sample_step=1)
    z_lo, z_hi = floors[0]
    rss(f"kerrokset {len(floors)}")

    probe = _lfs(paths, z_lo, z_hi, voxel_size=20.0, progress_cb=None)
    voxel = _auto_voxel(probe)
    del probe
    rss(f"auto-voxel {voxel:.1f} mm")

    cloud = _lfs(paths, z_lo, z_hi, voxel_size=voxel, progress_cb=None)
    rss(f"cloud {len(cloud.points):,}")
    cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    rss(f"cloud kohinasuodatettu {len(cloud.points):,}")

    if a.real:
        # Putki lataa thick/refine VASTA suodattimen jalkeen, joten niita ei
        # ladata tassakaan — muuten huippu mitattaisiin vaarasta lahtotasosta.
        from ordinate.core.segmentation.pointnet_filter import PointNetFilter
        filt = PointNetFilter()
        rss("PointNetFilter ladattu")
        out, labels = filt.filter_with_labels(cloud)
        rss(f"filter_with_labels valmis: {len(out.points):,} pistetta, "
            f"{0 if labels is None else len(labels._keys):,} avainta")
        print(f"\nHUIPPU {_PEAK[0]:.2f} GB")
        return

    rng = ply_z_range(paths[0])
    sc = ply_autoscale_factor(paths[0])
    zmn, zmx = rng[0] * sc, rng[1] * sc
    band_lo = zmn + 0.35 * (zmx - zmn)
    band_hi = zmn + 0.65 * (zmx - zmn)

    thick = _lfs(paths, band_lo, band_hi, voxel_size=0.0, progress_cb=None,
                 max_points=45_000_000)
    rss(f"thick_cloud {len(thick.points):,}")

    refine = _lfs(paths, z_lo, z_hi, voxel_size=5.0, progress_cb=None,
                  max_points=45_000_000)
    rss(f"refine_cloud {len(refine.points):,}")

    if a.skip_filter:
        print(f"\nHUIPPU {_PEAK[0]:.2f} GB")
        return

    from ordinate.core.segmentation.pointnet_filter import PointNetFilter
    filt = PointNetFilter()
    rss("PointNetFilter ladattu")
    _trace_classify(filt, np.asarray(cloud.points))

    print(f"\nHUIPPU {_PEAK[0]:.2f} GB")


if __name__ == "__main__":
    main()

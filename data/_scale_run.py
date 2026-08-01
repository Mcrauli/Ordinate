"""MITTAKAAVAMITTARI: ajaa tuotantoputken ja mittaa AIKA + HUIPPUMUISTI vaiheittain.

Iso kohde voi kaataa demon riippumatta laadusta. Tama kertoo kumpi rajoittaa
(muisti vai aika) ja MISSA vaiheessa -- arvailun sijaan.

Aja:  .venv\\Scripts\\python data/_scale_run.py data/_retail_s.ply --out data/output/_scale_s
"""
from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

import psutil


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cloud")
    ap.add_argument("--out", default="data/output/_scale")
    ap.add_argument("--detector", default="contour")
    ap.add_argument("--semantic", default="pointnet")
    a = ap.parse_args()

    proc = psutil.Process()
    peak = [0.0]
    stop = threading.Event()

    def _watch():
        while not stop.wait(0.5):
            rss = proc.memory_info().rss / 1e9
            if rss > peak[0]:
                peak[0] = rss

    t0 = time.time()
    marks: list[tuple[float, float, str]] = []

    def progress(msg: str) -> None:
        rss = proc.memory_info().rss / 1e9
        if rss > peak[0]:
            peak[0] = rss
        marks.append((time.time() - t0, rss, msg))
        print(f"[{time.time()-t0:7.1f}s {rss:5.1f}GB] {msg}", flush=True)

    threading.Thread(target=_watch, daemon=True).start()

    from scan2bim.core.pipeline import Pipeline, PipelineConfig

    cfg = PipelineConfig(detector=a.detector, auto_voxel=True,
                         semantic_filter_mode=a.semantic)
    pipe = Pipeline(cfg, progress=progress)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    err = None
    try:
        models = pipe.run_floors([Path(a.cloud)], out)
    except Exception as e:  # skaalaus voi kaataa -- se ON tulos
        import traceback
        traceback.print_exc()
        models, err = [], e
    stop.set()
    total = time.time() - t0

    print("\n=== VAIHEET (kumulatiivinen aika, RSS) ===")
    prev = 0.0
    for t, rss, msg in marks:
        print(f"  +{t - prev:6.1f}s  {t:7.1f}s  {rss:5.1f}GB  {msg[:88]}")
        prev = t
    print(f"\nYHTEENSA {total/60:.1f} min   HUIPPUMUISTI {peak[0]:.1f} GB")
    if err is not None:
        print(f"KAATUI: {type(err).__name__}: {err}")
        return
    for m in models:
        print(f"  kerros {m.metadata.floor_index}: {len(m.walls)} seinaa, "
              f"{len(m.spaces)} tilaa, {len(m.columns)} pilaria, "
              f"{len(m.openings)} aukkoa, voxel {m.metadata.voxel_size:.1f} mm")


if __name__ == "__main__":
    main()

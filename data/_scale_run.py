"""MITTAKAAVAMITTARI: ajaa tuotantoputken ja mittaa AIKA + HUIPPUMUISTI vaiheittain.

Iso kohde voi kaataa demon riippumatta laadusta. Tama kertoo kumpi rajoittaa
(muisti vai aika) ja MISSA vaiheessa -- arvailun sijaan.

Aja:  .venv\\Scripts\\python data/_scale_run.py data/_retail_s.ply --out data/output/_scale_s
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import psutil

# Putken progress-viesteissa on nuolia ja aakkosia; Windowsin cp1252-konsoli
# heittaa UnicodeEncodeError:n kesken ajon ja kaataa koko mittauksen.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cloud")
    ap.add_argument("--out", default="data/output/_scale")
    ap.add_argument("--detector", default="contour")
    ap.add_argument("--semantic", default="pointnet")
    ap.add_argument("--voxel", type=float, default=0.0,
                    help="pakota detektiovoxel (mm); 0 = auto")
    a = ap.parse_args()

    proc = psutil.Process()
    peak = [0.0]
    stop = threading.Event()

    # Huipun PAIKKA, ei vain arvo: viimeisin progress-viesti talteen kun uusi
    # huippu syntyy. Ilman tata huippu on pelkka luku eika kerro mita korjata.
    last_msg = ["(alku)"]
    peak_at = ["(alku)"]

    def _watch():
        while not stop.wait(0.5):
            rss = proc.memory_info().rss / 1e9
            if rss > peak[0]:
                peak[0] = rss
                peak_at[0] = last_msg[0]

    t0 = time.time()
    marks: list[tuple[float, float, str]] = []

    def progress(msg: str) -> None:
        rss = proc.memory_info().rss / 1e9
        if rss > peak[0]:
            peak[0] = rss
            peak_at[0] = msg
        last_msg[0] = msg
        marks.append((time.time() - t0, rss, msg))
        print(f"[{time.time()-t0:7.1f}s {rss:5.1f}GB] {msg}", flush=True)

    threading.Thread(target=_watch, daemon=True).start()

    from ordinate.core.pipeline import Pipeline, PipelineConfig

    cfg = PipelineConfig(detector=a.detector, auto_voxel=a.voxel <= 0.0,
                         voxel_size=a.voxel if a.voxel > 0.0 else 12.0,
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
    print(f"HUIPPU SYNTYI VAIHEESSA: {peak_at[0][:100]}")
    if err is not None:
        print(f"KAATUI: {type(err).__name__}: {err}")
        return
    for m in models:
        print(f"  kerros {m.metadata.floor_index}: {len(m.walls)} seinaa, "
              f"{len(m.spaces)} tilaa, {len(m.columns)} pilaria, "
              f"{len(m.openings)} aukkoa, voxel {m.metadata.voxel_size:.1f} mm")


if __name__ == "__main__":
    main()

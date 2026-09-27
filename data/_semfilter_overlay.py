"""Vision-overlay: tuotanto vs ehdokas suodatustulos rinnakkain.

Ylarivi front-view (xz), alarivi top-view (xy). Punainen = poistettu, harmaa =
sailytetty. Nakee silmalla sailyyko rakenne (seinat/palkit/portaat) ja lahteeko
kaluste. keep-rate ei erota rakenteen syomista kalustepoistosta — tama erottaa.
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.geometry.loader import load_point_cloud
from ordinate.core.segmentation.pointnet_filter import PointNetFilter, _slab_bands

REPO = Path(__file__).resolve().parent.parent


def _load_xyz_mm(src):
    src = Path(src)
    if (src / "coord.npy").exists() if src.is_dir() else False:
        return np.load(src / "coord.npy").astype(np.float64) * 1000.0
    return np.asarray(load_point_cloud(src).points, dtype=np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default=str(REPO / "data" / "_semfilter_overlay.png"))
    ap.add_argument("--max", type=int, default=300000)
    a = ap.parse_args()
    xyz = _load_xyz_mm(a.src)
    if len(xyz) > a.max:
        xyz = xyz[np.random.default_rng(0).choice(len(xyz), a.max, replace=False)]
    print(f"{a.src}: {len(xyz)} pistetta (naytteistetty)", flush=True)

    models = [("TUOTANTO", REPO / "models" / "s3dis_pointnet.onnx"),
              ("EHDOKAS", Path(a.model))]
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    for col, (tag, mp) in enumerate(models):
        f = PointNetFilter(model_path=mp)
        keep = f._classify(xyz) | _slab_bands(xyz)
        print(f"  {tag}: keep {100*keep.mean():.1f}%", flush=True)
        for row, (ci, cj, lab) in enumerate([(0, 2, "front xz"), (0, 1, "top xy")]):
            ax = axes[row, col]
            ax.scatter(xyz[keep, ci], xyz[keep, cj], s=0.2, c="0.5", linewidths=0)
            ax.scatter(xyz[~keep, ci], xyz[~keep, cj], s=0.2, c="red", linewidths=0)
            ax.set_aspect("equal"); ax.set_title(f"{tag} — {lab} (keep {100*keep.mean():.0f}%)")
    plt.tight_layout(); plt.savefig(a.out, dpi=80, bbox_inches="tight")
    print(f"saved {a.out}", flush=True)


if __name__ == "__main__":
    main()

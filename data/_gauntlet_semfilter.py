"""Gauntlet: mittaa semanttisen suodattimen keep-ratet OIKEALLA datalla.

Kolme ymparistoa:
  rohbau   : held-out site (EI koulutuksessa) — per-piste-GT → rakenne-saily +
             krassa-poisto tarkasti
  asunto   : SpatialLM-asunto — ei per-piste-GT → keep-rate + vertailu tuotantoon
  talo35   : SpatialLM-talo    — sama

Vertaa AINA nykyista tuotantomallia ja ehdokasta samoilla pilvilla samalla
inferenssipolulla (tuotannon PointNetFilter). Ehto: rakenne ei saa laskea.

Aja (.venv):
  python data/_gauntlet_semfilter.py --model models/_new/pointnet_geocol_retail.onnx
  python data/_gauntlet_semfilter.py            # pelkka tuotanto-baseline
"""
import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.geometry.loader import load_point_cloud
from ordinate.core.segmentation.pointnet_filter import PointNetFilter, _slab_bands

REPO = Path(__file__).resolve().parent.parent
DL = Path.home() / "Downloads"

# Rohbau class.npy → S3DIS (sama kartta kuin koulutuksessa)
_ROHBAU_STRUCT = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}   # katto/lattia/seina/palkki/pilari/ikkuna/ovi
_ROHBAU_REMOVE = {0, 17}                                                     # None/tausta + TGA(MEP)
_HELDOUT_SITES = ["site_02", "site_07", "site_10"]                           # EI koulutuksessa (1,4,13)


def _rohbau_scenes(n=2):
    out = []
    for s in _HELDOUT_SITES:
        for d in sorted(glob.glob(str(DL / "rohbau3d" / "train" / s / "scene_*")))[:n]:
            out.append(d)
    return out


def _eval_rohbau(filt, scene_dir):
    xyz = np.load(Path(scene_dir) / "coord.npy").astype(np.float64) * 1000.0   # m → mm
    cls = np.load(Path(scene_dir) / "class.npy").astype(np.int64).ravel()
    gt_struct = np.isin(cls, list(_ROHBAU_STRUCT))
    gt_remove = np.isin(cls, list(_ROHBAU_REMOVE))
    # sama maski kuin tuotannon filter(): luokitin + laattakaistojen pakkosailytys
    keep = filt._classify(xyz) | _slab_bands(xyz)
    sk = keep[gt_struct].mean() if gt_struct.any() else float("nan")
    rr = (~keep[gt_remove]).mean() if gt_remove.any() else float("nan")
    return sk, rr, len(xyz)


def _eval_keeprate(filt, ply):
    cloud = load_point_cloud(Path(ply))
    n0 = len(cloud.points)
    kept = len(filt.filter(cloud).points)
    return kept / max(n0, 1), n0


def _run_model(tag, model_path, skip_rohbau=False, skip_plys=False):
    print(f"\n########## {tag} ##########", flush=True)
    filt = PointNetFilter(model_path=model_path)
    print(f"malli ladattu: {filt.is_available()}  piirteita={getattr(filt, '_n_features', '?')}", flush=True)
    if not filt.is_available():
        print("  ONNX-mallia ei ladattu — ohitetaan"); return

    # --- rohbau (per-piste-GT) ---
    if skip_rohbau:
        print("\n[rohbau — ohitettu]", flush=True)
    else:
        print("\n[rohbau held-out — rakenne-saily (poisto ~0: paljas runko, ei kalusteita)]", flush=True)
    sks, rrs = [], []
    for d in ([] if skip_rohbau else _rohbau_scenes(2)):
        t = time.time()
        sk, rr, n = _eval_rohbau(filt, d)
        sks.append(sk); rrs.append(rr)
        print(f"  {Path(d).parent.name}/{Path(d).name}: rakenne={sk:.3f} poisto={rr:.3f} "
              f"({n} pist, {time.time()-t:.0f}s)", flush=True)
    if sks:
        print(f"  >> KESKIARVO rakenne={np.nanmean(sks):.3f}  poisto={np.nanmean(rrs):.3f}", flush=True)

    # --- asunto + talo35 (keep-rate) ---
    for name, pat in ([] if skip_plys else
                      [("asunto", DL / "spatiallm_apartment" / "scene_*_0.ply"),
                       ("talo35", DL / "spatiallm_talo_000035" / "scene_*_0.ply")]):
        plys = sorted(glob.glob(str(pat)))[:3]
        if not plys:
            print(f"\n[{name}] ei pilvia ({pat})"); continue
        print(f"\n[{name} — keep-rate]", flush=True)
        krs = []
        for p in plys:
            t = time.time()
            kr, n = _eval_keeprate(filt, p)
            krs.append(kr)
            print(f"  {Path(p).name}: keep={100*kr:.1f}%  ({n} pist, {time.time()-t:.0f}s)", flush=True)
        print(f"  >> KESKIARVO keep={100*np.mean(krs):.1f}%", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="ehdokas-ONNX; tyhja = vain tuotanto-baseline")
    ap.add_argument("--skip-rohbau", action="store_true", help="ohita hidas rohbau (~14 min/malli)")
    ap.add_argument("--skip-plys", action="store_true", help="ohita SpatialLM asunto/talo")
    ap.add_argument("--skip-prod", action="store_true", help="ohita tuotanto-baseline (jos jo mitattu)")
    a = ap.parse_args()
    prod = REPO / "models" / "s3dis_pointnet.onnx"
    if not a.skip_prod:
        _run_model("TUOTANTO (nykyinen)", prod, a.skip_rohbau, a.skip_plys)
    if a.model:
        _run_model(f"EHDOKAS ({Path(a.model).name})", Path(a.model), a.skip_rohbau, a.skip_plys)


if __name__ == "__main__":
    main()

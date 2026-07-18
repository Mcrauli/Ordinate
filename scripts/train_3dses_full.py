"""Täysi 3DSES + Rohbau -koulutus. Bronze+Silver (66 skeneä, 12-luokkaa,
kaluste=Clutter) + Gold (7, 18-luokkaa) luetaan SUORAAN zipistä (ei purkua).
Rohbau = runko. Rikkaat piirteet rgb+korkeus (10). Held-out osa skeneistä + S171.

KORJAA edellisen bugin: per-tier-taksonomia (Bronze/Silver=12lk, Gold=18lk),
label AINA viimeisestä sarakkeesta.

Aja (.venv_train):
  python train_3dses_full.py --zip 3DSES.zip --rohbau DIR --rtrain 1,4,13 --epochs 20 --out M.pth
"""
import sys, glob, time, argparse, zipfile, io
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
def _imp(n, p):
    s = importlib.util.spec_from_file_location(n, str(Path(__file__).parent / p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
E = _imp("exp", "export_s3dis_model.py"); FX = _imp("fx", "rohbau_feature_exp.py")
GEO = _imp("geo", "geo_feats.py")

# 12-luokka (Bronze/Silver) -> S3DIS 13. KEEP rakenne (0-6), REMOVE muut.
MAP12 = {0:3, 1:0, 2:6, 3:9, 4:9, 5:9, 6:2, 7:1, 8:1, 9:2, 10:5, 11:12}
# 18-luokka (Gold): 0 Column,1 Components,2 Covering,3 Damper,4 Door,5 Exit,
# 6 Fire,7 Furniture,8 Heater,9 Lamp,10 Outlet,11 Railing,12 Slab,13 Stair,
# 14 Switch,15 Wall,16 Window,17 Clutter
MAP18 = {0:3, 1:9, 2:0, 3:9, 4:6, 5:9, 6:9, 7:7, 8:9, 9:9, 10:9, 11:2, 12:1, 13:1, 14:9, 15:2, 16:5, 17:12}
_RM = [7, 8, 9, 10, 11, 12]


def _lut(mp):
    l = np.full(max(mp) + 1, 12, np.int64)
    for k, v in mp.items(): l[k] = v
    return l
LUT12, LUT18 = _lut(MAP12), _lut(MAP18)


def scene_blocks(z, name, mp_lut, voxel, max_bps, rng, geo=False):
    with z.open(name) as f: a = np.load(io.BytesIO(f.read()))
    xyz = a[:, :3].astype(np.float32)
    rgb = (a[:, 3:6].astype(np.float32)) / 255.0
    raw = a[:, -1].astype(np.int64)                 # label AINA viimeinen sarake
    raw = np.clip(raw, 0, len(mp_lut) - 1)
    lbl = mp_lut[raw]
    idx = FX._voxel_repr_idx(xyz, voxel); xyz, rgb, lbl = xyz[idx], rgb[idx], lbl[idx]
    fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
    cols = [rgb, h[:, None]]
    if geo: cols.append(GEO.compute(xyz))
    extra = np.column_stack(cols).astype(np.float32)
    bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
    if bf is None: return None, None
    if len(bf) > max_bps:
        p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
    return bf, bl


def dses_blocks(zip_path, tiers, voxel, max_bps, rng, holdout_frac=0.15, geo=False):
    z = zipfile.ZipFile(zip_path)
    tr_F, tr_L, va_F, va_L = [], [], [], []
    for tier, lut in tiers:
        names = sorted([n for n in z.namelist() if n.startswith(tier + "/") and n.endswith(".npy")])
        nva = max(1, int(len(names) * holdout_frac))
        for i, n in enumerate(names):
            bf, bl = scene_blocks(z, n, lut, voxel, max_bps, rng, geo=geo)
            if bf is None: continue
            if i < nva: va_F.append(bf); va_L.append(bl)
            else: tr_F.append(bf); tr_L.append(bl)
        print(f"  {tier}: {len(names)} skeneä (held-out {nva})", flush=True)
    return (np.vstack(tr_F), np.vstack(tr_L), np.vstack(va_F), np.vstack(va_L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True); ap.add_argument("--rohbau", required=True)
    ap.add_argument("--rtrain", default="1,4,13"); ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--voxel", type=float, default=0.03); ap.add_argument("--max-bps", type=int, default=200)
    ap.add_argument("--rmax", type=int, default=30); ap.add_argument("--out", default="")
    ap.add_argument("--arch", default="pointnet", choices=["pointnet", "dgcnn", "hybrid", "hybridpro"])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--cache", default="", help="npz-lohkovälimuisti — rakenna kerran, lataa jatkossa heti")
    ap.add_argument("--build-cache-only", action="store_true", help="rakenna vain välimuisti ja lopeta")
    ap.add_argument("--augment", action="store_true", help="data-augmentaatio (flip/kierto/jitter)")
    ap.add_argument("--geo", action="store_true", help="geometriset PCA-piirteet (verticality/planarity/sphericity)")
    ap.add_argument("--focal", action="store_true", help="focal loss (kohdistaa vaikeisiin rajatapauksiin)")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"device={device}", flush=True)
    rng = np.random.default_rng(13); t0 = time.time()
    if a.cache and Path(a.cache).exists():
        z = np.load(a.cache)
        tf, tl, dvf, dvl = z["tf"], z["tl"], z["dvf"], z["dvl"]
        print(f"lohkot VÄLIMUISTISTA {a.cache}: train {len(tf)}, held-out {len(dvf)} ({time.time()-t0:.0f}s)", flush=True)
    else:
        tiers = [("Bronze", LUT12), ("Silver", LUT12), ("Gold", LUT18)]
        dtf, dtl, dvf, dvl = dses_blocks(a.zip, tiers, a.voxel, a.max_bps, rng, geo=a.geo)
        r_tr = []
        for s in a.rtrain.split(","): r_tr += sorted(glob.glob(str(Path(a.rohbau) / f"site_{int(s):02d}" / "scene_*")))
        r_tr = r_tr[:a.rmax]
        rf, rl = FX._blocks(r_tr, a.voxel, True, a.max_bps, rng, geo=a.geo); rf = np.delete(rf, 9, axis=2)  # poista int (rgb+korkeus[+geo])
        tf = np.vstack([dtf, rf]); tl = np.vstack([dtl, rl])
        print(f"lohkot: 3DSES {len(dtf)} + Rohbau {len(rf)} = {len(tf)} train | held-out 3DSES {len(dvf)} ({time.time()-t0:.0f}s)", flush=True)
        if a.cache:
            np.savez(a.cache, tf=tf, tl=tl, dvf=dvf, dvl=dvl)
            print(f"välimuisti tallennettu: {a.cache}", flush=True)
    if a.build_cache_only:
        print("vain välimuisti pyydetty — lopetetaan.", flush=True); return
    in_ch = tf.shape[2]                           # koko kanavamäärä (base6 + extrat)
    model = FX._train(tf, tl, in_ch, a.epochs, device, f"3DSES-{a.arch}", arch=a.arch,
                      batch=a.batch, augment=a.augment, focal=a.focal)
    sk, rr = FX._eval(model, dvf, dvl, device)
    print(f"==> HELD-OUT 3DSES: rakenne-säilyy={sk:.3f}  kaluste/krääsä-poisto={rr:.3f}", flush=True)
    if a.out:
        import torch as T; T.save({"model_state_dict": model.state_dict(), "in_ch": in_ch}, a.out)
        print(f"malli tallennettu: {a.out} (in_ch={in_ch})", flush=True)


if __name__ == "__main__":
    main()

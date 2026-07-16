"""Yhdistetty koulutus: 3DSES Gold (OIKEA kaluste/MEP + labelit + väri) + Rohbau
(runko). Rikkaat piirteet rgb+korkeus (10) → toimii värillisillä pilvillä ilman
intensiteettiä (S170/S171). Gold-taksonomia (12 lk) -> S3DIS 13 lk.

Aja (.venv_train):
  python train_3dses_rohbau.py --gold DIR --rohbau DIR --rtrain 1,4 --epochs 20 --out M.pth
"""
import sys, glob, time, argparse
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
def _imp(n, p):
    s = importlib.util.spec_from_file_location(n, str(Path(__file__).parent / p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
E = _imp("exp", "export_s3dis_model.py")
FX = _imp("fx", "rohbau_feature_exp.py")

# 3DSES Gold (12 lk) -> S3DIS 13 lk. KEEP: rakenne (0-6). REMOVE: 9,12.
GOLD_MAP = {0:3, 1:0, 2:6, 3:9, 4:9, 5:9, 6:2, 7:1, 8:1, 9:2, 10:5, 11:12}
_RM = [7, 8, 9, 10, 11, 12]


def load_gold(path):
    a = np.load(path)
    xyz = a[:, :3].astype(np.float32)             # metrit
    rgb = (a[:, 3:6].astype(np.float32)) / 255.0
    raw = a[:, 7].astype(np.int64)
    lut = np.full(int(raw.max()) + 1, 12, np.int64)
    for k, v in GOLD_MAP.items():
        if k <= raw.max(): lut[k] = v
    return xyz, rgb, lut[raw]


def gold_blocks(dirs, voxel, max_bps, rng):
    F, L = [], []
    for d in dirs:
        xyz, rgb, lbl = load_gold(d)
        idx = FX._voxel_repr_idx(xyz, voxel); xyz, rgb, lbl = xyz[idx], rgb[idx], lbl[idx]
        fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
        extra = np.column_stack([rgb, h]).astype(np.float32)   # 4 -> 10 feat
        bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
        if bf is None: continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        F.append(bf); L.append(bl)
    return (np.vstack(F), np.vstack(L)) if F else (None, None)


def rohbau_blocks_rgbh(dirs, voxel, max_bps, rng):
    """Rohbau rgb+korkeus (pudota intensiteetti slotti 9)."""
    bf, bl = FX._blocks(dirs, voxel, True, max_bps, rng)   # 11 feat
    return np.delete(bf, 9, axis=2), bl                    # -> 10 feat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True); ap.add_argument("--rohbau", required=True)
    ap.add_argument("--rtrain", default="1,4"); ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--voxel", type=float, default=0.03); ap.add_argument("--max-bps", type=int, default=400)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"device={device}", flush=True)
    rng = np.random.default_rng(11)
    gold = sorted(glob.glob(str(Path(a.gold) / "*.npy")))
    g_tr, g_va = gold[:-2], gold[-2:]     # held-out 2 Gold-skeneä
    r_tr = []
    for s in a.rtrain.split(","): r_tr += sorted(glob.glob(str(Path(a.rohbau) / f"site_{int(s):02d}" / "scene_*")))
    r_tr = r_tr[:20]
    print(f"Gold train {len(g_tr)} held-out {len(g_va)} | Rohbau {len(r_tr)}", flush=True)
    t0 = time.time()
    gf, gl = gold_blocks(g_tr, a.voxel, a.max_bps, rng)
    rf, rl = rohbau_blocks_rgbh(r_tr, a.voxel, a.max_bps, rng)
    tf = np.vstack([gf, rf]); tl = np.vstack([gl, rl])
    vgf, vgl = gold_blocks(g_va, a.voxel, a.max_bps, rng)
    print(f"lohkot: Gold {len(gf)} + Rohbau {len(rf)} = {len(tf)} | val Gold {len(vgf)} ({time.time()-t0:.0f}s)", flush=True)
    model = FX._train(tf, tl, 10, a.epochs, device, "3DSES+ROHBAU")
    sk, rr = FX._eval(model, vgf, vgl, device)
    print(f"==> HELD-OUT Gold: rakenne-säilyy={sk:.3f}  krääsä/kaluste-poisto={rr:.3f}", flush=True)
    if a.out:
        import torch as T; T.save({"model_state_dict": model.state_dict(), "in_ch": 10}, a.out)
        print(f"malli tallennettu: {a.out}", flush=True)


if __name__ == "__main__":
    main()

"""De-risk-koe: parantaako intensiteetti+väri+korkeus rakenne/roska-erottelua
vs. pelkkä xyz. Kouluttaa BASELINE (9 piirrettä) ja RICH (11: rgb+int+korkeus)
samalla datalla, validoi HELD-OUT eri työmaalla. GPU jos saatavilla.

Aja (.venv_train):
  python rohbau_feature_exp.py --root DIR --train 1,4,7 --val 10 --epochs 12
"""
import sys, os, glob, time, argparse
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
_spec = importlib.util.spec_from_file_location("exp", str(Path(__file__).parent / "export_s3dis_model.py"))
E = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(E)

_STRUCT = [0, 1, 2, 3, 4, 5, 6]
_RM = [7, 8, 9, 10, 11, 12]


def _voxel_repr_idx(pts, voxel_m):
    """Voxel-harvennuksen edustaja-INDEKSIT (alkuperäiseen taulukkoon) → kaikki
    attribuutit (coord/intensity/color/class) indeksoidaan samoin, linjassa."""
    keys = np.floor(pts / voxel_m).astype(np.int64)
    key1d = keys[:, 0] * 10_000_000 + keys[:, 1] * 1_000 + keys[:, 2]
    order = np.argsort(key1d, kind="stable")
    _, first = np.unique(key1d[order], return_index=True)
    return order[first]


def _load_scene(d, voxel_m, rich):
    xyz = np.load(os.path.join(d, "coord.npy")).astype(np.float32)
    cls = np.load(os.path.join(d, "class.npy")).astype(np.int64).ravel()
    lbl = E._map_rohbau_labels(cls)
    idx = _voxel_repr_idx(xyz, voxel_m)
    pts, lbl = xyz[idx], lbl[idx]
    extra = None
    if rich:
        inten = np.load(os.path.join(d, "intensity.npy")).astype(np.float32).reshape(-1)[idx]
        color = np.load(os.path.join(d, "color.npy")).astype(np.float32).reshape(len(xyz), -1)[idx]
        # normalisoinnit: väri 0-1, intensiteetti robusti p2-p98, korkeus lattiasta / 3m
        color = color[:, :3] / (255.0 if color.max() > 1.5 else 1.0)
        lo, hi = np.percentile(inten, 2), np.percentile(inten, 98)
        inten = np.clip((inten - lo) / max(hi - lo, 1e-6), 0, 1)
        floor_z = np.percentile(pts[:, 2], 2)
        height = np.clip((pts[:, 2] - floor_z) / 3.0, 0, 1.5)
        extra = np.column_stack([color, inten, height]).astype(np.float32)  # (N,5)
    return pts, lbl, extra


def _blocks(scene_dirs, voxel_m, rich, max_bps, rng):
    F, L = [], []
    for d in scene_dirs:
        pts, lbl, extra = _load_scene(d, voxel_m, rich)
        bf, bl = E._pts_to_blocks(pts, lbl, block_m=1.0, n_pts=4096, stride_m=0.5, extra=extra)
        if bf is None:
            continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        F.append(bf); L.append(bl)
    return np.vstack(F), np.vstack(L)


def _eval(model, feats, lbls, device):
    import torch
    model.eval()
    sk = rr = 0.0
    with torch.no_grad():
        preds = []
        for i in range(0, len(feats), 16):
            x = torch.tensor(feats[i:i+16]).to(device)
            preds.append(model(x).argmax(-1).cpu().numpy())
    pred = np.concatenate(preds).ravel(); gt = lbls.ravel()
    gt_rm = np.isin(gt, _RM); pr_rm = np.isin(pred, _RM)
    sk = (~pr_rm[~gt_rm]).mean() if (~gt_rm).any() else 1.0   # rakenne säilyy
    rr = pr_rm[gt_rm].mean() if gt_rm.any() else 0.0          # krääsä poistuu
    return sk, rr


def _train(feats, lbls, in_ch, epochs, device, tag):
    import torch, torch.nn as nn, torch.optim as optim
    model = E._build_model(13, in_ch).to(device)
    counts = np.maximum(np.bincount(lbls.ravel(), minlength=13).astype(np.float32), 1)
    w = torch.tensor((1/counts)/(1/counts).sum()*13, dtype=torch.float32).to(device)
    opt = optim.Adam(model.parameters(), lr=1e-3)
    sch = optim.lr_scheduler.StepLR(opt, 6, 0.5)
    crit = nn.CrossEntropyLoss(weight=w)
    n = len(feats)
    for ep in range(epochs):
        model.train(); perm = np.random.permutation(n); losses = []
        for i in range(0, n, 8):
            bi = perm[i:i+8]
            x = torch.tensor(feats[bi]).to(device); y = torch.tensor(lbls[bi]).to(device)
            opt.zero_grad()
            loss = crit(model(x).reshape(-1, 13), y.reshape(-1))
            loss.backward(); opt.step(); losses.append(loss.item())
        sch.step()
        print(f"  [{tag}] epoch {ep+1}/{epochs} loss={sum(losses)/len(losses):.4f}", flush=True)
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--train", required=True); ap.add_argument("--val", required=True)
    ap.add_argument("--epochs", type=int, default=12); ap.add_argument("--voxel", type=float, default=0.03)
    ap.add_argument("--max-bps", type=int, default=250); ap.add_argument("--max-scenes", type=int, default=0)
    ap.add_argument("--rich-only", action="store_true")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device}", flush=True)
    root = Path(a.root); rng = np.random.default_rng(42)
    tr_sites = [f"site_{int(s):02d}" for s in a.train.split(",")]
    va_sites = [f"site_{int(s):02d}" for s in a.val.split(",")]
    tr_dirs, va_dirs = [], []
    for s in tr_sites: tr_dirs += sorted(glob.glob(str(root / s / "scene_*")))
    for s in va_sites: va_dirs += sorted(glob.glob(str(root / s / "scene_*")))
    if a.max_scenes:
        tr_dirs = tr_dirs[:a.max_scenes]; va_dirs = va_dirs[:max(2, a.max_scenes//3)]
    print(f"train {len(tr_dirs)} skeneä {tr_sites}, held-out {len(va_dirs)} {va_sites}", flush=True)

    runs = [(True, 11, "RICH rgb+int+h")] if a.rich_only else [(False, 9, "BASELINE xyz"), (True, 11, "RICH rgb+int+h")]
    for rich, in_ch, tag in runs:
        t0 = time.time()
        tf, tl = _blocks(tr_dirs, a.voxel, rich, a.max_bps, rng)
        vf, vl = _blocks(va_dirs, a.voxel, rich, a.max_bps, rng)
        print(f"[{tag}] lohkot train={len(tf)} val={len(vf)} ({time.time()-t0:.0f}s lataus)", flush=True)
        model = _train(tf, tl, in_ch, a.epochs, device, tag)
        sk, rr = _eval(model, vf, vl, device)
        print(f"==> [{tag}] HELD-OUT: rakenne-säilyy={sk:.3f}  krääsä-poisto={rr:.3f}", flush=True)


if __name__ == "__main__":
    main()

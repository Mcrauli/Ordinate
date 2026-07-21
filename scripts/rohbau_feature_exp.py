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


def _load_scene(d, voxel_m, rich, geo=False, colf=False, pairf=False):
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
        cols = [color, inten[:, None], height[:, None]]
        if geo:
            import importlib.util as _u
            _s = _u.spec_from_file_location("geo", str(Path(__file__).parent / "geo_feats.py"))
            _g = _u.module_from_spec(_s); _s.loader.exec_module(_g)
            cols.append(_g.compute(pts))
        if colf:
            import importlib.util as _u
            _s = _u.spec_from_file_location("col", str(Path(__file__).parent / "column_feats_v2.py"))
            _c = _u.module_from_spec(_s); _s.loader.exec_module(_c)
            cols.append(_c.compute(pts))
        if pairf:
            import importlib.util as _u
            _s = _u.spec_from_file_location("pair", str(Path(__file__).parent / "pair_feats.py"))
            _p = _u.module_from_spec(_s); _s.loader.exec_module(_p)
            cols.append(_p.compute(pts))
        extra = np.column_stack(cols).astype(np.float32)  # (N,5) tai (N,8) geo:lla
    return pts, lbl, extra


def _blocks(scene_dirs, voxel_m, rich, max_bps, rng, geo=False, colf=False, pairf=False):
    F, L = [], []
    for d in scene_dirs:
        pts, lbl, extra = _load_scene(d, voxel_m, rich, geo=geo, colf=colf, pairf=pairf)
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
        for i in range(0, len(feats), 4):
            x = torch.tensor(feats[i:i+4]).to(device)
            preds.append(model(x).argmax(-1).cpu().numpy())
    pred = np.concatenate(preds).ravel(); gt = lbls.ravel()
    gt_rm = np.isin(gt, _RM); pr_rm = np.isin(pred, _RM)
    sk = (~pr_rm[~gt_rm]).mean() if (~gt_rm).any() else 1.0   # rakenne säilyy
    rr = pr_rm[gt_rm].mean() if gt_rm.any() else 0.0          # krääsä poistuu
    return sk, rr


def _augment(x):
    """Lennossa: neliösymmetriat (flip x/y, xy-vaihto = eksaktit 90°-kierrot+
    peilaukset normalisoidulle lohkolle) + jitteri + väri-jitteri. Piirreslotit:
    0,1=xy_local 2=z 3,4=xy_scene 5=z 6-8=rgb 9=height."""
    import torch
    if torch.rand(1).item() < 0.5:                    # flip x
        x[..., 0] = 1 - x[..., 0]; x[..., 3] = 1 - x[..., 3]
    if torch.rand(1).item() < 0.5:                    # flip y
        x[..., 1] = 1 - x[..., 1]; x[..., 4] = 1 - x[..., 4]
    if torch.rand(1).item() < 0.5:                    # swap xy (90°)
        x[..., [0, 1]] = x[..., [1, 0]]; x[..., [3, 4]] = x[..., [4, 3]]
    x[..., 0:6] += torch.randn_like(x[..., 0:6]) * 0.01           # jitteri
    if x.shape[-1] >= 9:
        x[..., 6:9] = (x[..., 6:9] + torch.randn_like(x[..., 6:9]) * 0.03).clamp(0, 1)  # väri
    return x


def _train(feats, lbls, in_ch, epochs, device, tag, arch="pointnet", batch=8, augment=False, focal=False):
    import torch, torch.nn as nn, torch.optim as optim
    import torch.nn.functional as _F
    _builders = {"dgcnn": E._build_dgcnn, "hybrid": E._build_hybrid,
                 "hybridpro": E._build_hybrid_pro, "pointnet": E._build_model}
    model = _builders.get(arch, E._build_model)(13, in_ch).to(device)
    counts = np.maximum(np.bincount(lbls.ravel(), minlength=13).astype(np.float32), 1)
    w = torch.tensor((1/counts)/(1/counts).sum()*13, dtype=torch.float32).to(device)
    opt = optim.Adam(model.parameters(), lr=1e-3)
    sch = optim.lr_scheduler.StepLR(opt, 6, 0.5)
    ce = nn.CrossEntropyLoss(weight=w)
    def _focal(logits, y, gamma=2.0):    # painotettu focal: (1-p_t)^γ skaalaa helpot alas
        ce_pp = _F.cross_entropy(logits, y, weight=w, reduction="none")
        pt = torch.exp(-_F.cross_entropy(logits, y, reduction="none"))
        # HUOM: painotettu CE normalisoidaan painojen summalla (kuten
        # nn.CrossEntropyLoss), EI näytemäärällä — muuten käänteisfrekvenssi-
        # painot (~1e-5) kutistavat lossin ja gradientit ~1e6-kertaisesti.
        return ((1 - pt) ** gamma * ce_pp).sum() / w[y].sum().clamp(min=1e-8)
    crit = (lambda o, y: _focal(o, y)) if focal else ce
    n = len(feats)
    nb = (n + batch - 1) // batch
    heartbeat = max(1, nb // 8)          # ~8 progressiprinttiä/epoch → ei pitkää hiljaisuutta
    for ep in range(epochs):
        model.train(); perm = np.random.permutation(n); losses = []
        for j, i in enumerate(range(0, n, batch)):
            bi = perm[i:i+batch]
            x = torch.tensor(feats[bi]).to(device); y = torch.tensor(lbls[bi]).to(device)
            if augment: x = _augment(x)
            opt.zero_grad()
            loss = crit(model(x).reshape(-1, 13), y.reshape(-1))
            loss.backward(); opt.step(); losses.append(loss.item())
            if j % heartbeat == 0:
                print(f"    [{tag}] ep{ep+1} {j}/{nb} loss={loss.item():.3f}", flush=True)
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

"""Vie S3DIS PointNet -malli ONNX-muotoon → models/s3dis_pointnet.onnx.

Vaatii erikseen: pip install torch --index-url https://download.pytorch.org/whl/cpu

Vaihtoehto A — valmiit painot (suositeltu):
  1. Avaa: https://github.com/yanx27/Pointnet_Pointnet2_pytorch
  2. README → Pretrained models → S3DIS (Area-5) → pointnet_sem_seg → best_model.pth
  3. python scripts/export_s3dis_model.py --weights best_model.pth

Vaihtoehto B — harjoita synteettisellä datalla (ei ulkoisia tiedostoja tarvita):
  python scripts/export_s3dis_model.py --synth
  Generoi 500 virtuaalihuonetta (lattia/katto/seinät/huonekalut), harjoittaa
  ~30 min CPU:lla. Ei yhtä hyvä kuin A mutta toimii heti.

Vaihtoehto C — harjoita 3DSES-datalla jos löytyy oikeat labeltiedostot:
  python scripts/export_s3dis_model.py --train --data data/_3dses

Tulos: models/s3dis_pointnet.onnx
build.ps1 bundlaa sen automaattisesti exe:hen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Arkkitehtuuri — täsmälleen yanx27/Pointnet_Pointnet2_pytorch pointnet_sem_seg
# Samat parametrinimet → best_model.pth latautuu suoraan.
# ---------------------------------------------------------------------------

def _build_model(k: int = 13):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class _Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv1d(9, 64, 1)
            self.conv2 = nn.Conv1d(64, 128, 1)
            self.conv3 = nn.Conv1d(128, 1024, 1)
            self.bn1 = nn.BatchNorm1d(64)
            self.bn2 = nn.BatchNorm1d(128)
            self.bn3 = nn.BatchNorm1d(1024)

        def forward(self, x):           # (B, 9, N) → (B, 1088, N)
            B, _, N = x.size()
            x = F.relu(self.bn1(self.conv1(x)))
            pointfeat = x
            x = F.relu(self.bn2(self.conv2(x)))
            x = self.bn3(self.conv3(x))
            x = torch.max(x, 2, keepdim=True)[0]
            x = x.view(-1, 1024, 1).expand(-1, -1, N)
            return torch.cat([x, pointfeat], 1)

    class _Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.feat = _Encoder()
            self.conv1 = nn.Conv1d(1088, 512, 1)
            self.conv2 = nn.Conv1d(512, 256, 1)
            self.conv3 = nn.Conv1d(256, 128, 1)
            self.conv4 = nn.Conv1d(128, k, 1)
            self.bn1 = nn.BatchNorm1d(512)
            self.bn2 = nn.BatchNorm1d(256)
            self.bn3 = nn.BatchNorm1d(128)
            self.dropout = nn.Dropout(p=0.3)

        def forward(self, x):           # (B, N, 9) → (B, N, k)
            x = x.permute(0, 2, 1)
            x = self.feat(x)
            x = F.relu(self.bn1(self.conv1(x)))
            x = self.dropout(F.relu(self.bn2(self.conv2(x))))
            x = F.relu(self.bn3(self.conv3(x)))
            x = self.conv4(x)
            return x.permute(0, 2, 1)

    return _Model()


# ---------------------------------------------------------------------------
# Vaihtoehto A — lataa valmiit painot
# ---------------------------------------------------------------------------

def load_pretrained(model, path: Path) -> None:
    import torch
    ckpt = torch.load(str(path), map_location="cpu", weights_only=True)
    state = ckpt.get("model_state_dict") or ckpt.get("state_dict") or ckpt
    missing, _ = model.load_state_dict(state, strict=False)
    real_missing = [k for k in missing if "fstn" not in k]
    if real_missing:
        print(f"VAROITUS: puuttuvat avaimet: {real_missing[:5]}")
    else:
        print(f"Painot ladattu: {path}  ({path.stat().st_size//1024} KB)")


# ---------------------------------------------------------------------------
# Vaihtoehto B — synteettinen harjoitusdata
# ---------------------------------------------------------------------------

def _gen_retail_room(rng, n_pts: int = 120_000):
    """Synteettinen LIIKETILA: iso halli + lattia-katto-hyllyrivit (label 10)
    + tavaraa hyllyillä (label 12). Hyllyrivit läpäisevät geometrisen pysty-
    maskin ja näyttävät seiniltä — suodattimen on opittava ne pois."""
    import numpy as np

    W = rng.uniform(10.0, 25.0)
    D = rng.uniform(8.0, 20.0)
    H = rng.uniform(3.0, 5.0)
    density = n_pts / (2 * (W * D + W * H + D * H) + 0.001)

    pts_list, lbl_list = [], []

    def _emit(n, label):
        pts_list.append(n); lbl_list.append(np.full(len(n), label, dtype=np.int64))

    n_floor = max(200, int(density * W * D))
    xy = rng.uniform([0, 0], [W, D], (n_floor, 2))
    _emit(np.c_[xy, rng.normal(0.0, 0.004, n_floor)], 1)
    _emit(np.c_[xy + rng.uniform(-0.01, 0.01, (n_floor, 2)),
                rng.normal(H, 0.004, n_floor)], 0)

    for axis, fixed, lo, hi in [(0, 0.0, 0, D), (0, W, 0, D), (1, 0.0, 0, W), (1, D, 0, W)]:
        n_wall = max(100, int(density * (hi - lo) * H))
        u = rng.uniform(lo, hi, n_wall)
        v = rng.uniform(0.0, H, n_wall)
        noise = rng.normal(0, 0.004, n_wall)
        w = (np.c_[np.full(n_wall, fixed) + noise, u, v] if axis == 0
             else np.c_[u, np.full(n_wall, fixed) + noise, v])
        _emit(w, 2)

    # Hyllyrivit: yhdensuuntaiset, käytävävälein, LÄHES kattoon (myymälähylly
    # 2.0–2.5m tai varastohylly kattoon asti)
    n_rows = rng.integers(2, 6)
    aisle = rng.uniform(1.2, 2.5)
    shelf_d = rng.uniform(0.4, 1.0)
    y0 = rng.uniform(1.0, 2.5)
    for r in range(n_rows):
        ry = y0 + r * (shelf_d + aisle)
        if ry + shelf_d > D - 1.0:
            break
        sh_h = rng.uniform(2.0, H - rng.uniform(0.0, 0.4))
        x0 = rng.uniform(0.5, 2.0)
        x1 = W - rng.uniform(0.5, 2.0)
        seg_len = x1 - x0
        if seg_len < 2.0:
            continue
        # hyllyn päädyt + molemmat pitkät pystypinnat (kuin ohut "seinä")
        n_face = max(150, int(density * seg_len * sh_h))
        for fy in (ry, ry + shelf_d):
            u = rng.uniform(x0, x1, n_face)
            v = rng.uniform(0.0, sh_h, n_face)
            _emit(np.c_[u, np.full(n_face, fy) + rng.normal(0, 0.01, n_face), v], 10)
        # hyllytasot + tavaraa (epätasainen täyttö)
        n_lvl = rng.integers(3, 7)
        for lv in range(n_lvl):
            lz = (lv + 1) * sh_h / (n_lvl + 1)
            n_g = max(60, int(density * seg_len * shelf_d * 0.8))
            gx = rng.uniform(x0, x1, n_g)
            gy = rng.uniform(ry, ry + shelf_d, n_g)
            gz = lz + rng.uniform(0.0, 0.35, n_g)
            keep = rng.random(n_g) < rng.uniform(0.4, 0.9)
            if keep.any():
                _emit(np.c_[gx[keep], gy[keep], gz[keep]], 12)

    pts = np.vstack(pts_list).astype(np.float32)
    lbl = np.concatenate(lbl_list).astype(np.int64)
    return pts, lbl


def _gen_room(rng, n_pts: int = 80_000):
    """Generoi yksi synteettinen huone, palauttaa (pts Nx3, labels N) metreinä."""
    import numpy as np

    W = rng.uniform(3.0, 9.0)
    D = rng.uniform(3.0, 9.0)
    H = rng.uniform(2.4, 3.5)
    density = n_pts / (2 * (W * D + W * H + D * H) + 0.001)

    pts_list, lbl_list = [], []

    def _plane(n, label):
        pts_list.append(n); lbl_list.append(np.full(len(n), label, dtype=np.int64))

    # Lattia (label 1) + katto (label 0)
    n_floor = max(100, int(density * W * D))
    xy = rng.uniform([0, 0], [W, D], (n_floor, 2))
    z_floor = rng.normal(0.0, 0.003, n_floor)
    z_ceil  = rng.normal(H,   0.003, n_floor)
    floor_pts = np.c_[xy, z_floor]
    ceil_pts  = np.c_[xy + rng.uniform(-0.01, 0.01, (n_floor, 2)), z_ceil]
    _plane(floor_pts, 1); _plane(ceil_pts, 0)

    # Seinät (label 2) — 4 seinää
    for axis, fixed, lo, hi in [
        (0, 0.0, 0, D), (0, W,   0, D),
        (1, 0.0, 0, W), (1, D,   0, W),
    ]:
        n_wall = max(50, int(density * (hi - lo) * H))
        u = rng.uniform(lo, hi, n_wall)
        v = rng.uniform(0.0, H,  n_wall)
        noise = rng.normal(0, 0.004, n_wall)
        if axis == 0:
            w = np.c_[np.full(n_wall, fixed) + noise, u, v]
        else:
            w = np.c_[u, np.full(n_wall, fixed) + noise, v]
        _plane(w, 2)

    # Huonekalut — pöydät (label 7) ja tuolit (label 8)
    n_furniture = rng.integers(1, 8)
    for _ in range(n_furniture):
        kind = rng.integers(0, 3)      # 0=pöytä, 1=tuoli, 2=kaappi
        if kind == 0:                   # pöytä
            fw, fd = rng.uniform(0.6, 1.6), rng.uniform(0.6, 1.0)
            fh_bot, fh_top = sorted((rng.uniform(0.68, 0.75), rng.uniform(0.68, 0.75)))
            label = 7
        elif kind == 1:                 # tuoli
            fw, fd = rng.uniform(0.4, 0.6), rng.uniform(0.4, 0.6)
            fh_bot, fh_top = rng.uniform(0.42, 0.48), rng.uniform(0.80, 0.95)
            label = 8
        else:                           # kaappi/hylly
            fw, fd = rng.uniform(0.3, 0.6), rng.uniform(0.8, 1.8)
            fh_bot, fh_top = rng.uniform(0.0, 0.1), rng.uniform(0.9, 2.0)
            label = 10

        fx = rng.uniform(0.3, max(0.31, W - fw - 0.3))
        fy = rng.uniform(0.3, max(0.31, D - fd - 0.3))

        n_obj = max(30, int(density * 2 * (fw * fd + fw * (fh_top - fh_bot) + fd * (fh_top - fh_bot))))
        ox = rng.uniform(fx, fx + fw, n_obj)
        oy = rng.uniform(fy, fy + fd, n_obj)
        oz = rng.uniform(fh_bot, fh_top, n_obj)
        obj_pts = np.c_[ox, oy, oz] + rng.normal(0, 0.003, (n_obj, 3))
        _plane(obj_pts, label)

    pts = np.vstack(pts_list).astype(np.float32)
    lbl = np.concatenate(lbl_list).astype(np.int64)
    return pts, lbl


def _pts_to_blocks(pts, lbl, block_m: float = 1.0, n_pts: int = 4096, stride_m: float = 0.5):
    """Jakaa huoneen 1m×1m lohkoihin, palauttaa (feats (B,N,9), labels (B,N))."""
    import numpy as np

    sc_min = pts.min(0); sc_range = np.maximum(pts.max(0) - sc_min, 1e-6)
    x_steps = np.arange(sc_min[0], pts[:, 0].max() - block_m + 1e-6, stride_m)
    y_steps = np.arange(sc_min[1], pts[:, 1].max() - block_m + 1e-6, stride_m)

    blocks_f, blocks_l = [], []
    for cx in x_steps:
        for cy in y_steps:
            mask = (
                (pts[:, 0] >= cx) & (pts[:, 0] < cx + block_m) &
                (pts[:, 1] >= cy) & (pts[:, 1] < cy + block_m)
            )
            idx = np.where(mask)[0]
            if len(idx) < 32:
                continue
            if len(idx) >= n_pts:
                sel = np.random.choice(len(idx), n_pts, replace=False)
            else:
                sel = np.concatenate([np.arange(len(idx)),
                                       np.random.choice(len(idx), n_pts - len(idx))])
            s = pts[idx[sel]]
            f = np.zeros((n_pts, 9), dtype=np.float32)
            f[:, 0] = (s[:, 0] - cx) / block_m
            f[:, 1] = (s[:, 1] - cy) / block_m
            f[:, 2] = (s[:, 2] - sc_min[2]) / sc_range[2]
            f[:, 3] = (s[:, 0] - sc_min[0]) / sc_range[0]
            f[:, 4] = (s[:, 1] - sc_min[1]) / sc_range[1]
            f[:, 5] = (s[:, 2] - sc_min[2]) / sc_range[2]
            blocks_f.append(f)
            blocks_l.append(lbl[idx[sel]])

    if not blocks_f:
        return None, None
    return np.stack(blocks_f), np.stack(blocks_l)


def train_synthetic(model, n_rooms: int = 500, epochs: int = 80,
                    batch: int = 8, n_pts: int = 4096) -> None:
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.optim as optim

    rng = np.random.default_rng(42)
    print(f"Generoidaan {n_rooms} synteettistä huonetta...")

    all_feats, all_lbls = [], []
    for i in range(n_rooms):
        pts, lbl = _gen_room(rng)
        f, l = _pts_to_blocks(pts, lbl, n_pts=n_pts)
        if f is not None:
            all_feats.append(f); all_lbls.append(l)
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{n_rooms} huonetta")

    all_feats = np.vstack(all_feats)   # (total_blocks, N, 9)
    all_lbls  = np.vstack(all_lbls)    # (total_blocks, N)
    print(f"Lohkoja yhteensä: {len(all_feats)}")

    # Luokkapainot — kompensoi epätasapaino
    flat_lbls = all_lbls.ravel()
    counts = np.bincount(flat_lbls, minlength=13).astype(np.float32)
    counts = np.maximum(counts, 1)
    weights = torch.tensor(1.0 / counts, dtype=torch.float32)
    weights = weights / weights.sum() * 13          # normalisoi

    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=30, gamma=0.5)
    criterion = nn.CrossEntropyLoss(weight=weights)
    model.train()

    n_blocks = len(all_feats)
    steps_per_epoch = max(20, n_blocks // batch)

    for epoch in range(epochs):
        losses = []
        idx_all = np.random.permutation(n_blocks)
        for step in range(steps_per_epoch):
            bi = idx_all[step * batch % n_blocks: step * batch % n_blocks + batch]
            if len(bi) == 0:
                bi = idx_all[:batch]
            x = torch.tensor(all_feats[bi])   # (B, N, 9)
            y = torch.tensor(all_lbls[bi])     # (B, N)
            optimizer.zero_grad()
            logits = model(x)                  # (B, N, 13)
            loss = criterion(logits.reshape(-1, 13), y.reshape(-1))
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        scheduler.step()

        if (epoch + 1) % 10 == 0 or epoch == 0:
            avg = sum(losses) / len(losses)
            # Laske nopea tarkkuus
            with torch.no_grad():
                sample_x = torch.tensor(all_feats[:64])
                sample_y = all_lbls[:64].ravel()
                pred = model(sample_x).reshape(-1, 13).argmax(1).numpy()
                # Furniture vs structural acc
                is_furn_gt   = np.isin(sample_y, [7, 8, 9, 10, 11, 12])
                is_furn_pred = np.isin(pred,      [7, 8, 9, 10, 11, 12])
                struct_acc = (is_furn_gt == is_furn_pred).mean()
            print(f"Epoch {epoch+1:3d}/{epochs}  loss={avg:.4f}  struct/furn-acc={struct_acc:.3f}")

    print("Harjoitus valmis.")


# ---------------------------------------------------------------------------
# Vaihtoehto C — harjoita 3DSES-datalla (jos on oikeat labeltiedostot)
# ---------------------------------------------------------------------------

def _voxel_downsample(pts, lbl, voxel_m: float = 0.03):
    """Harvenna voxel-gridillä, säilytä yleisin label per voxel."""
    import numpy as np
    keys = np.floor(pts / voxel_m).astype(np.int64)
    key1d = keys[:, 0] * 10_000_000 + keys[:, 1] * 1_000 + keys[:, 2]
    order = np.argsort(key1d, kind="stable")
    key_s, pts_s, lbl_s = key1d[order], pts[order], lbl[order]
    _, first = np.unique(key_s, return_index=True)
    return pts_s[first], lbl_s[first]


def train_on_3dses(model, data_dir: Path, epochs: int = 50) -> None:
    import glob, numpy as np, torch, torch.nn as nn, torch.optim as optim
    import time

    files = sorted(glob.glob(str(data_dir / "*.npy")))
    if not files:
        print(f"Ei .npy-tiedostoja: {data_dir}")
        sys.exit(1)

    N_BLOCK = 4096
    print("Poimitaan lohkot etukäteen (kerran)...", flush=True)

    # Poimi lohkot per-tiedosto KERRAN → (B, 4096, 9) ja (B, 4096)
    all_feats, all_lbls = [], []
    for f in files:
        t0 = time.time()
        a = np.load(f)
        if a.ndim != 2 or a.shape[1] < 7:
            continue
        pts = a[:, :3].astype(np.float32)
        lbl = a[:, 6].astype(np.int64)
        # Harvenna 30 mm voxeliin → masking nopeutuu rajusti
        pts, lbl = _voxel_downsample(pts, lbl, 0.03)
        bf, bl = _pts_to_blocks(pts, lbl, block_m=1.0, n_pts=N_BLOCK, stride_m=0.5)
        if bf is not None:
            all_feats.append(bf); all_lbls.append(bl)
        print(f"  {Path(f).name}: {len(pts):,} pistetta (harvennettu) "
              f"-> {0 if bf is None else len(bf)} lohkoa  ({time.time()-t0:.0f}s)", flush=True)

    all_feats = np.vstack(all_feats)   # (total_blocks, 4096, 9)
    all_lbls  = np.vstack(all_lbls)    # (total_blocks, 4096)
    n_blocks  = len(all_feats)
    print(f"Lohkoja yhteensä: {n_blocks}", flush=True)

    # Luokkapainot epätasapainolle (kalusteita vähän → painota)
    counts = np.bincount(all_lbls.ravel(), minlength=13).astype(np.float32)
    counts = np.maximum(counts, 1)
    weights = torch.tensor((1.0 / counts) / (1.0 / counts).sum() * 13, dtype=torch.float32)

    BATCH = 8
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.5)
    criterion = nn.CrossEntropyLoss(weight=weights)
    model.train()

    for epoch in range(epochs):
        losses = []
        perm = np.random.permutation(n_blocks)
        for i in range(0, n_blocks, BATCH):
            bi = perm[i:i + BATCH]
            x = torch.tensor(all_feats[bi])
            y = torch.tensor(all_lbls[bi])
            optimizer.zero_grad()
            loss = criterion(model(x).reshape(-1, 13), y.reshape(-1))
            loss.backward(); optimizer.step(); losses.append(loss.item())
        scheduler.step()
        if losses:
            print(f"Epoch {epoch+1}/{epochs}  loss={sum(losses)/len(losses):.4f}", flush=True)


# ---------------------------------------------------------------------------
# ONNX-vienti
# ---------------------------------------------------------------------------

def export_onnx(model, out_path: Path, n_pts: int = 4096) -> None:
    import torch
    model.eval()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Tallenna painot ENSIN — jos ONNX-vienti kaatuu, harjoitus ei mene hukkaan.
    ckpt_path = out_path.with_suffix(".pth")
    torch.save(model.state_dict(), str(ckpt_path))
    print(f"Painot tallennettu: {ckpt_path}", flush=True)

    dummy = torch.zeros(1, n_pts, 9)
    torch.onnx.export(
        model, dummy, str(out_path),
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {1: "N"}, "output": {1: "N"}},
        opset_version=17,
        dynamo=False,          # käytä vakaata legacy-vientiä (ei vaadi onnxscriptia)
    )
    print(f"Viety: {out_path}  ({out_path.stat().st_size//1024} KB)")
    print("Kopioi models/-hakemistoon ja aja build.ps1.")


# ---------------------------------------------------------------------------

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_default = repo_root / "models" / "s3dis_pointnet.onnx"

    ap = argparse.ArgumentParser(description="Vie S3DIS PointNet ONNX-muotoon")
    ap.add_argument("--weights", type=Path, default=None,
                    help="Pretrained .pth (Pointnet_Pointnet2_pytorch pointnet_sem_seg)")
    ap.add_argument("--synth", action="store_true",
                    help="Harjoita synteettisellä datalla (ei ulkoisia tiedostoja)")
    ap.add_argument("--synth-rooms", type=int, default=500,
                    help="Synteettisten huoneiden määrä (oletus 500)")
    ap.add_argument("--synth-epochs", type=int, default=80,
                    help="Harjoitusepokit (oletus 80)")
    ap.add_argument("--train", action="store_true",
                    help="Harjoita 3DSES-datalla (--data pakollinen)")
    ap.add_argument("--data", type=Path, default=repo_root / "data" / "_3dses")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--out", type=Path, default=out_default)
    args = ap.parse_args()

    try:
        import torch  # noqa: F401
    except ImportError:
        print("PyTorch puuttuu.")
        print("Asenna: pip install torch --index-url https://download.pytorch.org/whl/cpu")
        sys.exit(1)

    model = _build_model(k=13)

    if args.weights:
        if not args.weights.exists():
            print(f"Tiedostoa ei löydy: {args.weights}"); sys.exit(1)
        load_pretrained(model, args.weights)
    elif args.synth:
        train_synthetic(model, n_rooms=args.synth_rooms, epochs=args.synth_epochs)
    elif args.train:
        train_on_3dses(model, args.data, epochs=args.epochs)
    else:
        print("Käytä: --weights <pth>  tai  --synth  tai  --train --data <hakemisto>")
        sys.exit(1)

    export_onnx(model, args.out)


if __name__ == "__main__":
    main()

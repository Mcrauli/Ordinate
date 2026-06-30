"""Vie S3DIS PointNet -malli ONNX-muotoon → models/s3dis_pointnet.onnx.

Vaatii erikseen: pip install torch --index-url https://download.pytorch.org/whl/cpu

Kaksi polkua:

A) Pretrained-painot Pointnet_Pointnet2_pytorch-reposta (suositeltu):
   1. Lataa checkpoint:
      https://github.com/yanx27/Pointnet_Pointnet2_pytorch  → log/sem_seg/ → best_model.pth
   2. python scripts/export_s3dis_model.py --weights best_model.pth

B) Harjoita itse 3DSES-datalla (jos ei pretrained-painoja):
   python scripts/export_s3dis_model.py --train --data data/_3dses

Tulos: models/s3dis_pointnet.onnx  (bundlataan automaattisesti exe:hen build.ps1:llä)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# PointNet semanttinen segmentointimalli (9 piirrettä → 13 S3DIS-luokkaa)
# Identtinen Pointnet_Pointnet2_pytorch sem_seg -arkkitehtuurin kanssa.
# Input:  (B, N, 9)  — xyz_local + xyz_scene + rgb
# Output: (B, N, 13) — per-piste luokkalogitit
# ---------------------------------------------------------------------------

def _build_model():
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class PointNetSemSeg(nn.Module):
        def __init__(self, num_classes: int = 13, in_ch: int = 9) -> None:
            super().__init__()
            self.enc1 = nn.Sequential(nn.Conv1d(in_ch, 64,   1), nn.BatchNorm1d(64),   nn.ReLU())
            self.enc2 = nn.Sequential(nn.Conv1d(64,  128,    1), nn.BatchNorm1d(128),  nn.ReLU())
            self.enc3 = nn.Sequential(nn.Conv1d(128, 1024,   1), nn.BatchNorm1d(1024), nn.ReLU())
            self.dec1 = nn.Sequential(nn.Conv1d(1024+128+64, 512, 1), nn.BatchNorm1d(512), nn.ReLU())
            self.dec2 = nn.Sequential(nn.Conv1d(512, 256, 1), nn.BatchNorm1d(256), nn.ReLU(), nn.Dropout(0.5))
            self.out  = nn.Conv1d(256, num_classes, 1)

        def forward(self, x):   # x: (B, N, 9) → (B, N, 13)
            x = x.permute(0, 2, 1)          # (B, 9, N)
            f1 = self.enc1(x)               # (B, 64, N)
            f2 = self.enc2(f1)              # (B, 128, N)
            f3 = self.enc3(f2)              # (B, 1024, N)
            g  = f3.max(dim=2, keepdim=True)[0].expand_as(f3)  # (B, 1024, N)
            cat = torch.cat([f1, f2, g], 1) # (B, 1216, N)
            out = self.out(self.dec2(self.dec1(cat)))  # (B, 13, N)
            return out.permute(0, 2, 1)     # (B, N, 13)

    return PointNetSemSeg()


def export_onnx(model, out_path: Path, n_pts: int = 4096) -> None:
    import torch
    model.eval()
    dummy = torch.zeros(1, n_pts, 9)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model, dummy, str(out_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {1: "N"}, "output": {1: "N"}},
        opset_version=17,
    )
    print(f"Viety: {out_path}  ({out_path.stat().st_size // 1024} KB)")


def load_pretrained(model, weights_path: Path) -> None:
    import torch
    ckpt = torch.load(str(weights_path), map_location="cpu")
    state = ckpt.get("model_state_dict") or ckpt.get("state_dict") or ckpt
    # Pointnet_Pointnet2_pytorch käyttää hieman eri nimitystä — kokeile suoraan
    missing, unexpected = model.load_state_dict(state, strict=False)
    if missing:
        print(f"Puuttuvat avaimet: {missing[:5]}")
    if unexpected:
        print(f"Ylimääräiset avaimet: {unexpected[:5]}")
    print(f"Painot ladattu: {weights_path}")


# ---------------------------------------------------------------------------
# Harjoitus 3DSES-datalla (B polku)
# ---------------------------------------------------------------------------

def train_on_3dses(model, data_dir: Path, epochs: int = 50) -> None:
    import glob
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.optim as optim

    # 3DSES: *.npy tiedostot, muoto Nx7 (XYZ + normals/rgb + label)
    files = sorted(glob.glob(str(data_dir / "*.npy")))
    if not files:
        print(f"Ei .npy-tiedostoja hakemistossa {data_dir}")
        sys.exit(1)

    print(f"Harjoitusdata: {len(files)} tiedostoa, {data_dir}")

    # Oletetaan Nx7: xyz(0:3) + ...  + label(6)
    all_pts, all_labels = [], []
    for f in files:
        a = np.load(f)
        if a.ndim != 2 or a.shape[1] < 7:
            continue
        all_pts.append(a[:, :3].astype(np.float32))
        all_labels.append(a[:, 6].astype(np.int64))

    if not all_pts:
        print("Ei kelvollista dataa")
        sys.exit(1)

    pts   = np.vstack(all_pts)
    lbls  = np.concatenate(all_labels)
    print(f"Pisteitä yhteensä: {len(pts):,}, luokkia: {np.unique(lbls)}")

    # Yksinkertainen minibatch-harjoitus lohkoilla
    N_BLOCK, BATCH = 4096, 8
    sc_min = pts.min(0); sc_range = np.maximum(pts.max(0) - sc_min, 1.0)
    block_size = 1.0  # metreissä (3DSES on metreissä)

    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()
    model.train()

    for epoch in range(epochs):
        # Satunnaiset lohkot per epoch
        losses = []
        n_batches = max(20, len(pts) // (N_BLOCK * BATCH))
        for _ in range(n_batches):
            batch_feats, batch_lbls = [], []
            for _ in range(BATCH):
                cx = np.random.uniform(sc_min[0], pts[:, 0].max() - block_size)
                cy = np.random.uniform(sc_min[1], pts[:, 1].max() - block_size)
                mask = (
                    (pts[:, 0] >= cx) & (pts[:, 0] < cx + block_size) &
                    (pts[:, 1] >= cy) & (pts[:, 1] < cy + block_size)
                )
                idx = np.where(mask)[0]
                if len(idx) < 32:
                    continue
                sel = (np.random.choice(len(idx), N_BLOCK)
                       if len(idx) >= N_BLOCK else
                       np.concatenate([np.arange(len(idx)),
                                       np.random.choice(len(idx), N_BLOCK - len(idx))]))
                s = pts[idx[sel]]
                feat = np.zeros((N_BLOCK, 9), dtype=np.float32)
                feat[:, 0] = (s[:, 0] - cx) / block_size
                feat[:, 1] = (s[:, 1] - cy) / block_size
                feat[:, 2] = (s[:, 2] - sc_min[2]) / sc_range[2]
                feat[:, 3] = (s[:, 0] - sc_min[0]) / sc_range[0]
                feat[:, 4] = (s[:, 1] - sc_min[1]) / sc_range[1]
                feat[:, 5] = (s[:, 2] - sc_min[2]) / sc_range[2]
                batch_feats.append(feat)
                batch_lbls.append(lbls[idx[sel]])

            if not batch_feats:
                continue
            x = torch.tensor(np.stack(batch_feats))      # (B, N, 9)
            y = torch.tensor(np.stack(batch_lbls))        # (B, N)
            optimizer.zero_grad()
            logits = model(x)                             # (B, N, 13)
            loss = criterion(logits.reshape(-1, 13), y.reshape(-1))
            loss.backward()
            optimizer.step()
            losses.append(loss.item())

        if losses:
            print(f"Epoch {epoch+1}/{epochs}  loss={sum(losses)/len(losses):.4f}")

    print("Harjoitus valmis.")


# ---------------------------------------------------------------------------

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_default = repo_root / "models" / "s3dis_pointnet.onnx"

    ap = argparse.ArgumentParser(description="Vie S3DIS PointNet ONNX-muotoon")
    ap.add_argument("--weights", type=Path, default=None,
                    help="Pretrained .pth checkpoint (Pointnet_Pointnet2_pytorch)")
    ap.add_argument("--train", action="store_true",
                    help="Harjoita itse 3DSES-datalla (--data pakollinen)")
    ap.add_argument("--data", type=Path, default=repo_root / "data" / "_3dses",
                    help="3DSES .npy-hakemisto (oletus: data/_3dses)")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--out", type=Path, default=out_default)
    args = ap.parse_args()

    try:
        import torch  # noqa: F401
    except ImportError:
        print("PyTorch puuttuu. Asenna: pip install torch --index-url https://download.pytorch.org/whl/cpu")
        sys.exit(1)

    model = _build_model()

    if args.weights:
        load_pretrained(model, args.weights)
    elif args.train:
        train_on_3dses(model, args.data, epochs=args.epochs)
    else:
        print("HUOM: Ei painoja eikä harjoitusta — viedään satunnaiset painot (ei käyttökelpoinen).")
        print("Käytä: --weights <checkpoint.pth>  tai  --train --data data/_3dses")

    export_onnx(model, args.out)


if __name__ == "__main__":
    main()

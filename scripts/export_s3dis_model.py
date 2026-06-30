"""Vie S3DIS PointNet -malli ONNX-muotoon → models/s3dis_pointnet.onnx.

Vaatii erikseen: pip install torch --index-url https://download.pytorch.org/whl/cpu

Vaihtoehto A — valmiit painot (suositeltu, nopea):
  1. Avaa: https://github.com/yanx27/Pointnet_Pointnet2_pytorch
  2. README → Pretrained models → S3DIS (Area-5) → pointnet_sem_seg → best_model.pth
     (Google Drive -linkki, ~10 MB)
  3. Tallenna best_model.pth mihin tahansa ja aja:
       python scripts/export_s3dis_model.py --weights best_model.pth

Vaihtoehto B — harjoita itse 3DSES-datalla:
  python scripts/export_s3dis_model.py --train --data data/_3dses

Tulos: models/s3dis_pointnet.onnx
build.ps1 bundlaa sen automaattisesti exe:hen.

--- Mikä tämä malli on ---
Stanford S3DIS -datasetti: tuhansia käsinlabeloituja 3D-sisätilaskannauksia
joissa jokainen piste on merkitty 13:een luokkaan. PointNet-neuroverkko on
harjoitettu tunnistamaan nämä luokat. Me lainaamme ne valmiit "opit" (painot)
ja muunnamme ONNX-muotoon joka pyörii exe:ssä ilman GPU:ta tai PyTorchia.

Luokat:
  PIDETÄÄN (rakenteet):  0 katto  1 lattia  2 seinä  3 palkki  4 pilari  5 ikkuna  6 ovi
  POISTETAAN (kalusteet): 7 pöytä  8 tuoli  9 sohva  10 kaappi  11 taulu  12 krääsä
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Täsmälleen sama arkkitehtuuri kuin yanx27/Pointnet_Pointnet2_pytorch
# models/pointnet_sem_seg.py  (global_feat=False, feature_transform=False, channel=9)
# Samat parametrinimet → checkpoint latautuu suoraan.
# ---------------------------------------------------------------------------

def _build_model():
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
            pointfeat = x               # (B, 64, N)
            x = F.relu(self.bn2(self.conv2(x)))
            x = self.bn3(self.conv3(x))
            x = torch.max(x, 2, keepdim=True)[0]
            x = x.view(-1, 1024, 1).expand(-1, -1, N)
            return torch.cat([x, pointfeat], 1)  # (B, 1088, N)

    class _Model(nn.Module):
        """Parametrinimet vastaavat täysin Pointnet_Pointnet2_pytorch checkpointia."""
        def __init__(self, k=13):
            super().__init__()
            self.k = k
            self.feat = _Encoder()
            self.conv1 = nn.Conv1d(1088, 512, 1)
            self.conv2 = nn.Conv1d(512, 256, 1)
            self.conv3 = nn.Conv1d(256, 128, 1)
            self.conv4 = nn.Conv1d(128, k, 1)
            self.bn1 = nn.BatchNorm1d(512)
            self.bn2 = nn.BatchNorm1d(256)
            self.bn3 = nn.BatchNorm1d(128)
            self.dropout = nn.Dropout(p=0.3)

        def forward(self, x):           # (B, N, 9) → (B, N, 13)  raw logits
            x = x.permute(0, 2, 1)     # (B, 9, N)
            x = self.feat(x)            # (B, 1088, N)
            x = F.relu(self.bn1(self.conv1(x)))
            x = self.dropout(F.relu(self.bn2(self.conv2(x))))
            x = F.relu(self.bn3(self.conv3(x)))
            x = self.conv4(x)           # (B, 13, N)
            return x.permute(0, 2, 1)   # (B, N, 13)

    return _Model()


def load_pretrained(model, path: Path) -> None:
    import torch
    ckpt = torch.load(str(path), map_location="cpu", weights_only=True)
    state = ckpt.get("model_state_dict") or ckpt.get("state_dict") or ckpt

    missing, unexpected = model.load_state_dict(state, strict=False)
    # fstn-avaimet esiintyvät jos checkpoint on harjoitettu feature_transform=True:llä → ok
    real_missing = [k for k in missing if "fstn" not in k]
    if real_missing:
        print(f"VAROITUS: puuttuvat avaimet ({len(real_missing)}): {real_missing[:5]}")
        print("Checkpoint ei ehkä täsmää — kokeile --train -vaihtoehtoa.")
    else:
        size_kb = path.stat().st_size // 1024
        print(f"Painot ladattu onnistuneesti: {path}  ({size_kb} KB)")


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
    size_kb = out_path.stat().st_size // 1024
    print(f"Viety: {out_path}  ({size_kb} KB)")
    print("Kopioi models/-hakemistoon (tai se on jo siellä) ja aja build.ps1.")


# ---------------------------------------------------------------------------
# Vaihtoehto B — harjoitus 3DSES-datalla
# ---------------------------------------------------------------------------

def train_on_3dses(model, data_dir: Path, epochs: int = 50) -> None:
    import glob
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.optim as optim

    files = sorted(glob.glob(str(data_dir / "*.npy")))
    if not files:
        print(f"Ei .npy-tiedostoja: {data_dir}")
        sys.exit(1)

    print(f"Harjoitusdata: {len(files)} tiedostoa")

    all_pts, all_labels = [], []
    for f in files:
        a = np.load(f)
        if a.ndim != 2 or a.shape[1] < 7:
            continue
        all_pts.append(a[:, :3].astype(np.float32))
        all_labels.append(a[:, 6].astype(np.int64))

    if not all_pts:
        print("Ei kelvollista dataa (Nx7 npy odotetaan)")
        sys.exit(1)

    pts = np.vstack(all_pts)
    lbls = np.concatenate(all_labels)
    print(f"Pisteitä: {len(pts):,}  luokat: {sorted(map(int, np.unique(lbls)))}")

    N_BLOCK, BATCH = 4096, 8
    sc_min = pts.min(0)
    sc_range = np.maximum(pts.max(0) - sc_min, 1.0)
    block_m = 1.0  # 3DSES on metreissä

    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()
    model.train()

    for epoch in range(epochs):
        losses = []
        n_batches = max(20, len(pts) // (N_BLOCK * BATCH))
        for _ in range(n_batches):
            batch_feats, batch_lbls = [], []
            for _ in range(BATCH):
                cx = np.random.uniform(sc_min[0], pts[:, 0].max() - block_m)
                cy = np.random.uniform(sc_min[1], pts[:, 1].max() - block_m)
                mask = (
                    (pts[:, 0] >= cx) & (pts[:, 0] < cx + block_m) &
                    (pts[:, 1] >= cy) & (pts[:, 1] < cy + block_m)
                )
                idx = np.where(mask)[0]
                if len(idx) < 32:
                    continue
                if len(idx) >= N_BLOCK:
                    sel = np.random.choice(len(idx), N_BLOCK, replace=False)
                else:
                    sel = np.concatenate([
                        np.arange(len(idx)),
                        np.random.choice(len(idx), N_BLOCK - len(idx))
                    ])
                s = pts[idx[sel]]
                feat = np.zeros((N_BLOCK, 9), dtype=np.float32)
                feat[:, 0] = (s[:, 0] - cx) / block_m
                feat[:, 1] = (s[:, 1] - cy) / block_m
                feat[:, 2] = (s[:, 2] - sc_min[2]) / sc_range[2]
                feat[:, 3] = (s[:, 0] - sc_min[0]) / sc_range[0]
                feat[:, 4] = (s[:, 1] - sc_min[1]) / sc_range[1]
                feat[:, 5] = (s[:, 2] - sc_min[2]) / sc_range[2]
                batch_feats.append(feat)
                batch_lbls.append(lbls[idx[sel]])

            if not batch_feats:
                continue
            x = torch.tensor(np.stack(batch_feats))
            y = torch.tensor(np.stack(batch_lbls))
            optimizer.zero_grad()
            logits = model(x)
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

    ap = argparse.ArgumentParser(
        description="Vie S3DIS PointNet ONNX-muotoon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Mistä saada best_model.pth (Vaihtoehto A):
  https://github.com/yanx27/Pointnet_Pointnet2_pytorch
  README → Pretrained models → S3DIS (Area-5) → pointnet_sem_seg → best_model.pth
""",
    )
    ap.add_argument("--weights", type=Path, default=None,
                    help="Pretrained .pth (Pointnet_Pointnet2_pytorch pointnet_sem_seg)")
    ap.add_argument("--train", action="store_true",
                    help="Harjoita 3DSES-datalla (--data pakollinen)")
    ap.add_argument("--data", type=Path, default=repo_root / "data" / "_3dses",
                    help="3DSES .npy-hakemisto")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--out", type=Path, default=out_default)
    args = ap.parse_args()

    try:
        import torch  # noqa: F401
    except ImportError:
        print("PyTorch puuttuu.")
        print("Asenna: pip install torch --index-url https://download.pytorch.org/whl/cpu")
        sys.exit(1)

    model = _build_model()

    if args.weights:
        if not args.weights.exists():
            print(f"Tiedostoa ei löydy: {args.weights}")
            sys.exit(1)
        load_pretrained(model, args.weights)
    elif args.train:
        train_on_3dses(model, args.data, epochs=args.epochs)
    else:
        print("HUOM: Ei painoja eikä harjoitusta → viedään satunnaiset painot (ei käyttökelpoinen).")
        print("Käytä: --weights best_model.pth  tai  --train --data data/_3dses")

    export_onnx(model, args.out)


if __name__ == "__main__":
    main()

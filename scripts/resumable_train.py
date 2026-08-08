"""Resumable chunked trainer — survives ~4 min background-job kills.

Loads a prebuilt block cache (npz: tf/tl/dvf/dvl, 16ch), optionally drops rgb
to the deploy-compatible 13ch, and trains a few epochs per invocation, saving a
checkpoint (model+optimizer+scheduler+epoch) each time. Re-run until --epochs
reached; the final run exports ONNX (dynamic batch+N) next to the checkpoint.

  python resumable_train.py --cache C.npz --ckpt M.ckpt --epochs 14 --chunk 3 \
      --no-rgb --focal --augment [--out-onnx M.onnx]
"""
import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np


def _imp(name, rel):
    p = str(Path(__file__).resolve().parent / rel)
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


E = _imp("exp", "export_s3dis_model.py")
FX = _imp("fx", "rohbau_feature_exp.py")


def _export_onnx(model, in_ch, out, torch):
    model.eval()
    dummy = torch.zeros(1, 4096, in_ch)
    torch.onnx.export(
        model, dummy, str(out),
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "B", 1: "N"}, "output": {0: "B", 1: "N"}},
        opset_version=17, dynamo=False,
    )
    print(f"exported {out} in_ch={in_ch} {out.stat().st_size // 1024} KB", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--chunk", type=int, default=3)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--no-rgb", action="store_true")
    ap.add_argument("--focal", action="store_true")
    ap.add_argument("--augment", action="store_true")
    ap.add_argument("--out-onnx", default="")
    a = ap.parse_args()

    import time
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torch.nn.functional as _F
    t0 = time.time()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    z = np.load(a.cache)
    tf, tl, dvf, dvl = z["tf"], z["tl"], z["dvf"], z["dvl"]
    if a.no_rgb:
        keep = [0, 1, 2, 3, 4, 5] + list(range(9, tf.shape[2]))
        tf, dvf = tf[:, :, keep], dvf[:, :, keep]
    in_ch = tf.shape[2]
    print(f"device={device} cache={Path(a.cache).name} train={len(tf)} held-out={len(dvf)} in_ch={in_ch} ({time.time()-t0:.0f}s)", flush=True)

    model = E._build_model(13, in_ch).to(device)
    counts = np.maximum(np.bincount(tl.ravel(), minlength=13).astype(np.float32), 1)
    w = torch.tensor((1 / counts) / (1 / counts).sum() * 13, dtype=torch.float32).to(device)
    opt = optim.Adam(model.parameters(), lr=1e-3)
    sch = optim.lr_scheduler.StepLR(opt, 6, 0.5)
    ce = nn.CrossEntropyLoss(weight=w)

    def _focal(logits, y, gamma=2.0):
        ce_pp = _F.cross_entropy(logits, y, weight=w, reduction="none")
        pt = torch.exp(-_F.cross_entropy(logits, y, reduction="none"))
        return ((1 - pt) ** gamma * ce_pp).sum() / w[y].sum().clamp(min=1e-8)
    crit = (lambda o, y: _focal(o, y)) if a.focal else ce

    start_ep = 0
    ckpt = Path(a.ckpt)
    if ckpt.exists():
        st = torch.load(str(ckpt), map_location=device)
        model.load_state_dict(st["model"]); opt.load_state_dict(st["opt"])
        sch.load_state_dict(st["sch"]); start_ep = int(st["epoch"])
        print(f"resumed from {ckpt.name} at epoch {start_ep}", flush=True)

    if start_ep >= a.epochs:
        print(f"already at target {a.epochs} epochs", flush=True)
    else:
        n = len(tf); batch = a.batch
        nb = (n + batch - 1) // batch
        hb = max(1, nb // 6)
        end_ep = min(start_ep + a.chunk, a.epochs)
        # Checkpoint after EVERY epoch: the harness kills long jobs at ~4 min, so
        # per-epoch saves mean a kill loses at most one epoch; rerun resumes.
        for ep in range(start_ep, end_ep):
            model.train(); perm = np.random.permutation(n); losses = []
            for j, i in enumerate(range(0, n, batch)):
                bi = perm[i:i + batch]
                x = torch.tensor(tf[bi]).to(device); y = torch.tensor(tl[bi]).to(device)
                if a.augment:
                    x = FX._augment(x)
                opt.zero_grad()
                loss = crit(model(x).reshape(-1, 13), y.reshape(-1))
                loss.backward(); opt.step(); losses.append(loss.item())
                if j % hb == 0:
                    print(f"  ep{ep+1} {j}/{nb} loss={loss.item():.3f} ({time.time()-t0:.0f}s)", flush=True)
            sch.step()
            torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                        "sch": sch.state_dict(), "epoch": ep + 1, "in_ch": in_ch}, str(ckpt))
            print(f"epoch {ep+1}/{a.epochs} loss={sum(losses)/len(losses):.4f} SAVED ({time.time()-t0:.0f}s)", flush=True)
        start_ep = end_ep

    if start_ep >= a.epochs:
        sk, rr = FX._eval(model, dvf, dvl, device)
        print(f"==> HELD-OUT rakenne={sk:.3f} poisto={rr:.3f}", flush=True)
        if a.out_onnx:
            _export_onnx(model, in_ch, Path(a.out_onnx), torch)
        print("TRAINING COMPLETE", flush=True)
    else:
        print(f"MORE: rerun to continue ({start_ep}/{a.epochs})", flush=True)


if __name__ == "__main__":
    main()

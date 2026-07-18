"""Kontrolloitu ablaatio: auttavatko geometriset PCA-piirteet? Sama geo-cache,
DGCNN kahdesti — täysi 13ch (geo) vs sama data viipaloituna 10ch (ei geoa). Ainoa
muuttuja = geo-kanavat. Molemmille held-out + bias-pyyhkäisy (operointipiste).

Aja (.venv_train):
  python geo_ablation.py --cache CACHE_GEO.npz --epochs 30 --batch 8 [--focal] [--out-geo M.pth]
"""
import sys, argparse
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
def _imp(n, p):
    s = importlib.util.spec_from_file_location(n, str(Path(__file__).parent / p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
FX = _imp("fx", "rohbau_feature_exp.py")

_RM = [7, 8, 9, 10, 11, 12]


def _sweep(model, dvf, dvl, device):
    import torch
    model.eval(); logits = []
    with torch.no_grad():
        for i in range(0, len(dvf), 4):
            logits.append(model(torch.tensor(dvf[i:i+4]).to(device)).cpu().numpy())
    lg = np.concatenate(logits).reshape(-1, 13); gt = dvl.ravel(); gt_rm = np.isin(gt, _RM)
    rows = []
    for b in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        lg2 = lg.copy(); lg2[:, _RM] += b; pred = lg2.argmax(1); pr_rm = np.isin(pred, _RM)
        sk = (~pr_rm[~gt_rm]).mean(); rr = pr_rm[gt_rm].mean(); rows.append((b, sk, rr))
    return rows


def _run(tag, tf, tl, dvf, dvl, in_ch, a, device, out=""):
    print(f"\n===== {tag} (in_ch={in_ch}) =====", flush=True)
    model = FX._train(tf, tl, in_ch, a.epochs, device, tag, arch="dgcnn",
                      batch=a.batch, augment=True, focal=a.focal)
    sk, rr = FX._eval(model, dvf, dvl, device)
    print(f"==> [{tag}] HELD-OUT rakenne={sk:.3f} poisto={rr:.3f}", flush=True)
    print(f"    bias-pyyhkäisy [{tag}]:", flush=True)
    for b, s, r in _sweep(model, dvf, dvl, device):
        print(f"      b={b:.1f}  rakenne={s:.3f}  poisto={r:.3f}", flush=True)
    if out:
        import torch as T; T.save({"model_state_dict": model.state_dict(), "in_ch": in_ch}, out)
        print(f"    tallennettu: {out}", flush=True)
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--epochs", type=int, default=30); ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--focal", action="store_true")
    ap.add_argument("--out-geo", default=""); ap.add_argument("--skip-control", action="store_true")
    ap.add_argument("--skip-geo", action="store_true", help="aja vain CONTROL (jos GEO jo mitattu)")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"device={device}", flush=True)
    z = np.load(a.cache); tf, tl, dvf, dvl = z["tf"], z["tl"], z["dvf"], z["dvl"]
    ng = tf.shape[2]                                  # 13 (base6+rgb3+h1+geo3)
    print(f"cache: train {len(tf)} held-out {len(dvf)}  kanavia={ng}", flush=True)
    # GEO = täysi; CONTROL = pudota 3 viimeistä kanavaa (geo) → identtiset blokit
    if not a.skip_geo:
        _run("GEO", tf, tl, dvf, dvl, ng, a, device, out=a.out_geo)
    if not a.skip_control:
        _run("CONTROL(ei-geo)", tf[:, :, :ng-3], tl, dvf[:, :, :ng-3], dvl, ng-3, a, device)


if __name__ == "__main__":
    main()

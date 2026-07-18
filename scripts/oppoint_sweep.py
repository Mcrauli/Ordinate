"""Operating-point-pyyhkäisy: Hybrid Pro säilyttää rakenteen erinomaisesti
(0.953) mutta poistaa kalusteet varovaisesti (0.687). Lisätään kaluste-luokkien
(_RM=7..12) logiteille bias b ennen argmaxia ja mitataan held-out rakenne/poisto
eri b:llä. Näyttää voiko konservatiivisen mallin operointipisteen siirtää
paremmaksi ILMAN uudelleenkoulutusta.

Aja (.venv_train):
  python oppoint_sweep.py --cache CACHE.npz --model models/_new/hybridpro_3dses.pth
"""
import sys, argparse
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
def _imp(n, p):
    s = importlib.util.spec_from_file_location(n, str(Path(__file__).parent / p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
E = _imp("exp", "export_s3dis_model.py")

_RM = [7, 8, 9, 10, 11, 12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--arch", default="hybridpro")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    z = np.load(a.cache); dvf, dvl = z["dvf"], z["dvl"]
    builders = {"hybridpro": E._build_hybrid_pro, "dgcnn": E._build_dgcnn}
    ck = torch.load(a.model, map_location=device)
    model = builders[a.arch](13, ck.get("in_ch", 10)).to(device)
    model.load_state_dict(ck["model_state_dict"]); model.eval()
    # kerää raakalogitit kerran
    logits = []
    with torch.no_grad():
        for i in range(0, len(dvf), 4):
            x = torch.tensor(dvf[i:i+4]).to(device)
            logits.append(model(x).cpu().numpy())
    lg = np.concatenate(logits).reshape(-1, 13)     # (N,13)
    gt = dvl.ravel()
    gt_rm = np.isin(gt, _RM)
    print(f"held-out pisteitä {len(gt)}, kalustetta {gt_rm.sum()} ({gt_rm.mean()*100:.1f}%)", flush=True)
    print(f"{'bias':>6} {'rakenne':>8} {'poisto':>8}", flush=True)
    for b in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
        lg2 = lg.copy(); lg2[:, _RM] += b
        pred = lg2.argmax(1)
        pr_rm = np.isin(pred, _RM)
        sk = (~pr_rm[~gt_rm]).mean()      # rakenne säilyy (ei-kaluste ei mene poistoon)
        rr = pr_rm[gt_rm].mean()          # kaluste poistuu
        print(f"{b:>6.1f} {sk:>8.3f} {rr:>8.3f}", flush=True)


if __name__ == "__main__":
    main()

"""Ensemble-arviointi: keskiarvoistaa N mallin logitit samalla held-outilla ja
vertaa jokaiseen yksittäiseen malliin bias-pyyhkäisyn käyrällä. Vastaa kysymykseen
"kannattaako ensemble" ILMAN uutta koulutusta — pelkkä eteenpäinajo.

Mallit on koulutettava samalla cachella (sama held-out), muuten vertailu on
epäreilu; skripti tarkistaa in_ch:n ja kaatuu jos kanavamäärä ei täsmää dataan.

Aja (.venv_train):
  python ensemble_eval.py --cache CACHE.npz --models A.pth B.pth [--arch dgcnn]
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
_BIAS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]


def _logits(path, arch, dvf, device):
    import torch
    builders = {"dgcnn": E._build_dgcnn, "hybrid": E._build_hybrid,
                "hybridpro": E._build_hybrid_pro, "pointnet": E._build_model}
    ck = torch.load(path, map_location=device)
    in_ch = ck.get("in_ch", 10)
    if in_ch != dvf.shape[2]:
        raise SystemExit(f"{path}: in_ch={in_ch} != cachen kanavat {dvf.shape[2]} — eri data, ei vertailukelpoinen")
    model = builders[arch](13, in_ch).to(device)
    model.load_state_dict(ck["model_state_dict"]); model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(dvf), 4):
            out.append(model(torch.tensor(dvf[i:i+4]).to(device)).cpu().numpy())
    return np.concatenate(out).reshape(-1, 13)


def _curve(lg, gt_rm, tag):
    print(f"  [{tag}]", flush=True)
    rows = []
    for b in _BIAS:
        lg2 = lg.copy(); lg2[:, _RM] += b
        pr_rm = np.isin(lg2.argmax(1), _RM)
        sk = (~pr_rm[~gt_rm]).mean(); rr = pr_rm[gt_rm].mean()
        print(f"    b={b:.1f}  rakenne={sk:.3f}  poisto={rr:.3f}", flush=True)
        rows.append((sk, rr))
    return rows


def _interp(rows, sk_target):
    """Poisto interpoloituna annetulle rakennetasolle (käyrä on laskeva sk:ssa)."""
    sks = np.array([r[0] for r in rows]); rrs = np.array([r[1] for r in rows])
    # toleranssi: käyräpisteet on pyöristetty tulostuksessa, joten esim. 0.96794
    # ei saa pudottaa tavoitetta 0.968 pois vertailusta (piilottaisi parhaan mallin)
    tol = 1e-3
    if sk_target > sks.max() + tol or sk_target < sks.min() - tol:
        return None
    sk_target = float(np.clip(sk_target, sks.min(), sks.max()))
    o = np.argsort(sks)
    return float(np.interp(sk_target, sks[o], rrs[o]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--arch", default="dgcnn")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    z = np.load(a.cache); dvf, dvl = z["dvf"], z["dvl"]
    gt_rm = np.isin(dvl.ravel(), _RM)
    print(f"device={device}  held-out {len(dvf)} lohkoa, kalustetta {gt_rm.mean()*100:.1f}%", flush=True)

    singles, lgs = [], []
    for m in a.models:
        lg = _logits(m, a.arch, dvf, device); lgs.append(lg)
        singles.append(_curve(lg, gt_rm, Path(m).stem))
    # keskiarvo softmaxeista (kalibroidumpi kuin raakalogittien keskiarvo)
    from scipy.special import softmax
    ens = np.log(np.mean([softmax(l, axis=1) for l in lgs], axis=0) + 1e-12)
    ens_rows = _curve(ens, gt_rm, f"ENSEMBLE x{len(lgs)}")

    print("\n=== ero rakennetasoittain (ensemble - paras yksittäinen) ===", flush=True)
    for sk_t in [0.968, 0.95, 0.93, 0.90, 0.88]:
        e = _interp(ens_rows, sk_t)
        bs = [v for v in (_interp(s, sk_t) for s in singles) if v is not None]
        if e is None or not bs:
            print(f"  rakenne={sk_t:.3f}  (käyrän ulkopuolella)", flush=True); continue
        print(f"  rakenne={sk_t:.3f}  ensemble={e:.3f}  paras_yksittäinen={max(bs):.3f}  ero={e-max(bs):+.3f}", flush=True)


if __name__ == "__main__":
    main()

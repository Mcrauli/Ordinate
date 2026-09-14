"""Montako korjausta per-projekti-oppiminen tarvitsee? (oppimiskayra)

`_perproj_probe.py` mittasi "puolet korjattuna" eli kellarissa 104 seinaa.
Tuotteessa kukaan ei korjaa sataa seinaa ennen kuin hyotyy jostain. Tama ajaa
saman kokeen kiintealla koulutusmaaralla n ja arvioi LOPUILLA seinilla.

Oletus tuotteesta: kayttaja KATSOO n seinaa ja poistaa niista valeet — eli
myos pidetty seina on label (aito). Pelkat poistot eivat riita, koska malli
tarvitsee molemmat luokat. Jos tama ei pida, tulos ei pade.

Kaytto:
  _perproj_curve.py <model.json> <scene_dir> [nimi]
  _perproj_curve.py <model.json> <pilvi.ply> [nimi] --labels <labels.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _perproj_probe import _auc, _feat, _fit_logreg  # noqa: E402

_NS = (10, 20, 40, 80)
_REPS = 60


def _rows(model_json: str, scene: str):
    W = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    d = Path(scene)
    labels = None
    if "--labels" in sys.argv:
        labels = json.loads(Path(sys.argv[sys.argv.index("--labels") + 1])
                            .read_text(encoding="utf-8"))
        W = [(i, w) for i, w in enumerate(W) if str(i) in labels]
    else:
        W = list(enumerate(W))
    if d.is_dir():
        P = np.load(d / "coord.npy").astype(np.float64)
        C = np.load(d / "class.npy")
    else:
        import open3d as o3d
        P = np.asarray(o3d.io.read_point_cloud(str(d)).points)
        C = np.zeros(len(P), np.int16)
    if len(P) and float(np.ptp(P[:, 0])) < 500.0:
        P = P * 1000.0
    lens = [float(np.linalg.norm(np.asarray(w["axis"][-1], float)[:2]
                                 - np.asarray(w["axis"][0], float)[:2])) for _, w in W]
    med_len = float(np.median(lens)) if lens else 1.0
    rows = []
    for i, w in W:
        f = _feat(w, P, C, med_len)
        if not f:
            continue
        if labels is not None:
            f["_truth"] = float(labels[str(i)])
        rows.append(f)
    return rows


def main(model_json: str, scene: str, tag: str = "", *_rest) -> None:
    rows = _rows(model_json, scene)
    keys = [k for k in rows[0] if not k.startswith("_")]
    X = np.array([[r[k] for k in keys] for r in rows], float)
    y = np.array([1.0 if r["_truth"] >= 0.5 else 0.0 for r in rows])
    n_all, n_fake = len(y), int((1 - y).sum())
    print(f"\n{tag or Path(scene).name}: {n_all} seinaa, valeita {n_fake} "
          f"({n_fake / max(n_all, 1):.0%})")
    print(f"  {'n':>4}  {'AUC':>13}  {'1-piirre':>8}  {'valeista pois':>13}  "
          f"{'aidoista pois':>13}  {'top20 valeita':>13}  {'sattuma':>7}  {'kelvot':>6}")
    rng = np.random.default_rng(0)
    for n in _NS:
        if n >= n_all - 5:
            break
        aucs, singles, removed, lost, top, base, ok = [], [], [], [], [], [], 0
        for _ in range(_REPS):
            idx = rng.permutation(n_all)
            tr, te = idx[:n], idx[n:]
            if y[tr].sum() < 2 or (1 - y[tr]).sum() < 2:
                continue
            if y[te].sum() < 1 or (1 - y[te]).sum() < 1:
                continue
            ok += 1
            f, _, _, _ = _fit_logreg(X[tr], y[tr])
            st = f(X[te])
            aucs.append(_auc(st, y[te]))
            sc = [max(_auc(X[tr][:, j], y[tr]), 1 - _auc(X[tr][:, j], y[tr]))
                  for j in range(X.shape[1])]
            j = int(np.nanargmax(sc))
            sgn = 1 if _auc(X[tr][:, j], y[tr]) >= 0.5 else -1
            singles.append(_auc(sgn * X[te][:, j], y[te]))
            thr = float(np.min(f(X[tr][y[tr] > 0.5])))
            removed.append(float((st[y[te] < 0.5] < thr).mean()))
            lost.append(float((st[y[te] > 0.5] < thr).mean()))
            k = min(20, len(te))
            top.append(float((y[te][np.argsort(st)[:k]] < 0.5).mean()))
            base.append(float((y[te] < 0.5).mean()))
        if not ok:
            print(f"  {n:>4}  ei kelvollisia arvontoja (koulutukseen ei osu kumpaakin luokkaa)")
            continue
        a, s = np.array(aucs), np.array(singles)
        print(f"  {n:>4}  {np.nanmean(a):.3f} +-{np.nanstd(a):.3f}  {np.nanmean(s):8.3f}  "
              f"{np.mean(removed):13.0%}  {np.mean(lost):13.0%}  "
              f"{np.mean(top):13.0%}  {np.mean(base):7.0%}  {ok:>3}/{_REPS}")


if __name__ == "__main__":
    main(*sys.argv[1:])

"""Riittaako KAHDENKYMMENEN seinan korjaus siivoamaan loput? (per-projekti-oppiminen)

Lahes jokainen kumottu korjaus tassa projektissa on muotoa "kynnys X toimii
rakennuksessa A ja kaataa rakennuksen B". Se ei todista signaaleja tyhjiksi
vaan sen etta PAINO on rakennuskohtainen. Ja opittu aukkomalli mitattiin
samaan suuntaan: saman kohteen sisalla 2.4x saantoja parempi, toisessa
rakennuksessa sattuman tasolla.

Tama testaa suoraan sen tuoteidean: arkkitehti korjaa osan seinista, ja
sovellus oppii NIISTA korjauksista mika tassa rakennuksessa erottaa aidon
seinan valeseinasta. Labelit tulevat GT:sta, eli koe simuloi korjauksia
ilman etta kenenkaan tarvitsee labeloida mitaan.

Vertailukohta on ANTELIAS: paras yhden piirteen kynnys samalla foldilla —
eli se mita kasin viritetty globaali portti parhaimmillaan olisi.

Kaytto: _perproj_probe.py <model.json> <scene_dir> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

FACE = {5, 6, 8, 15}
_WAIST = (0.30, 0.70)


def _feat(w, P, C, med_len):
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][-1], float)[:2]
    L = float(np.linalg.norm(b - a))
    if L < 300.0:
        return None
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    th = float(w.get("thickness") or 200.0)
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    zlo, zhi = z0 + _WAIST[0] * h, z0 + _WAIST[1] * h
    d = P[:, :2] - a
    t, perp, z = d @ u, d @ n, P[:, 2]
    inb = (t > 0) & (t < L) & (z > zlo) & (z < zhi)
    half = th / 2.0
    face = inb & (np.abs(np.abs(perp) - half) < 60.0)
    if int(face.sum()) < 60:
        return None
    truth = float(np.isin(C[face], list(FACE)).mean())

    pf = perp[face]
    sign = 1.0 if np.median(pf) > 0 else -1.0
    dom = pf[np.sign(pf) == sign]
    flat = float(np.median(np.abs(dom - np.median(dom)))) if len(dom) > 20 else 99.0

    side = inb & (np.abs(perp) > half + 750.0) & (np.abs(perp) < half + 1250.0)
    on, off = int(face.sum()), int(side.sum())
    contrast = (on / max(off, 1)) if off else float(on)

    zf = z[face]
    hspan = float(np.percentile(zf, 98) - np.percentile(zf, 2)) / max(h, 1.0)
    htop = float(np.percentile(zf, 98) - z0) / max(h, 1.0)

    behind = inb & (sign * perp < -(half + 150.0)) & (sign * perp > -(half + 1300.0))
    front = inb & (sign * perp > half + 150.0) & (sign * perp < half + 1300.0)
    body = int(behind.sum()) / max(int(behind.sum()) + int(front.sum()), 1)

    cols = np.clip(((t[face] / L) * 16).astype(int), 0, 15)
    tops = np.array([np.percentile(zf[cols == i], 95) if (cols == i).sum() > 15
                     else np.nan for i in range(16)])
    topvar = float(np.nanstd(tops)) / max(h, 1.0) if np.isfinite(tops).sum() > 3 else 0.0
    cover = float(np.unique(cols).size / 16.0)

    return {
        "len": L / max(med_len, 1.0), "logpts": np.log10(max(on, 1)) ,
        "thick": th / 200.0, "conf": float(w.get("confidence") or 0.0),
        "support": float(w.get("support") or 0.0),
        "cont": float(w.get("continuity") or 0.0),
        "flat": min(flat, 60.0) / 20.0, "contrast": min(contrast, 20.0),
        "hspan": hspan, "htop": htop, "body": body, "topvar": min(topvar, 1.0),
        "cover": cover, "_truth": truth,
    }


def _fit_logreg(X, y, iters=900, lr=0.25, l2=0.05):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1]); b = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Z @ w + b)))
        g = Z.T @ (p - y) / len(y) + l2 * w
        w -= lr * g
        b -= lr * float((p - y).mean())
    return lambda A: 1.0 / (1.0 + np.exp(-(((A - mu) / sd) @ w + b))), w, mu, sd


def _auc(s, y):
    p, n = s[y > 0.5], s[y < 0.5]
    if not len(p) or not len(n):
        return float("nan")
    return float((p[:, None] > n[None, :]).mean() + 0.5 * (p[:, None] == n[None, :]).mean())


def main(model_json: str, scene: str, tag: str = "") -> None:
    W = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    d = Path(scene)
    P = np.load(d / "coord.npy").astype(np.float64)
    if float(np.ptp(P[:, 0])) < 500.0:
        P = P * 1000.0
    C = np.load(d / "class.npy")
    lens = [float(np.linalg.norm(np.asarray(w["axis"][-1], float)[:2]
                                 - np.asarray(w["axis"][0], float)[:2])) for w in W]
    med_len = float(np.median(lens)) if lens else 1.0
    rows = [f for f in (_feat(w, P, C, med_len) for w in W) if f]
    if len(rows) < 8:
        print(f"{tag or d.name}: liian vahan seinia ({len(rows)})"); return
    keys = [k for k in rows[0] if not k.startswith("_")]
    X = np.array([[r[k] for k in keys] for r in rows], float)
    y = np.array([1.0 if r["_truth"] >= 0.5 else 0.0 for r in rows])
    name = tag or d.name
    print(f"\n{name}: {len(y):.0f} seinaa, aitoja {int(y.sum())}, valeita {int((1-y).sum())}")
    if y.sum() < 3 or (1 - y).sum() < 3:
        print("  liian yksipuolinen jakauma vertailuun"); return

    rng = np.random.default_rng(0)
    aucs, best_single = [], []
    for rep in range(20):
        idx = rng.permutation(len(y))
        h = len(y) // 2
        tr, te = idx[:h], idx[h:]
        if y[tr].sum() < 2 or (1 - y[tr]).sum() < 2:
            continue
        f, wgt, _, _ = _fit_logreg(X[tr], y[tr])
        aucs.append(_auc(f(X[te]), y[te]))
        # antelias vertailukohta: paras YKSI piirre, kynnys valittu samasta foldista
        bs = max(max(_auc(X[tr][:, j], y[tr]), 1 - _auc(X[tr][:, j], y[tr]))
                 for j in range(X.shape[1]))
        j = int(np.argmax([max(_auc(X[tr][:, k], y[tr]), 1 - _auc(X[tr][:, k], y[tr]))
                           for k in range(X.shape[1])]))
        s = X[te][:, j] * (1 if _auc(X[tr][:, j], y[tr]) >= 0.5 else -1)
        best_single.append(_auc(s, y[te]))
    a = np.array([x for x in aucs if np.isfinite(x)])
    b = np.array([x for x in best_single if np.isfinite(x)])
    # Tuotekysymys ei ole AUC vaan: kuinka moni VALESEINA lahtee kun yhtaan
    # aitoa ei saa menettaa. Kynnys valitaan KOULUTUSpuoliskosta.
    kept, removed, lost = [], [], []
    for rep in range(20):
        idx = rng.permutation(len(y))
        hh = len(y) // 2
        tr, te = idx[:hh], idx[hh:]
        if y[tr].sum() < 2 or (1 - y[tr]).sum() < 2:
            continue
        f, _, _, _ = _fit_logreg(X[tr], y[tr])
        thr = float(np.min(f(X[tr][y[tr] > 0.5])))
        st = f(X[te])
        real, fake = y[te] > 0.5, y[te] < 0.5
        if not fake.any():
            continue
        removed.append(float((st[fake] < thr).mean()))
        lost.append(float((st[real] < thr).mean()))
    if removed:
        print(f"  kynnys 'ei menetta yhtaan aitoa koulutuksessa': "
              f"valeista poistuu {np.mean(removed):.0%}, aidoista menetetaan "
              f"{np.mean(lost):.0%}")
    print(f"  PUOLET korjattuna -> loput:   yhdistelma AUC {a.mean():.3f} "
          f"(+-{a.std():.3f})   paras yksi piirre {b.mean():.3f}")
    f, wgt, _, _ = _fit_logreg(X, y)
    order = np.argsort(-np.abs(wgt))
    print("  painavimmat piirteet: " +
          ", ".join(f"{keys[i]} {wgt[i]:+.2f}" for i in order[:5]))


if __name__ == "__main__":
    main(*sys.argv[1:])

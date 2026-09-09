"""Opittu aukkodetektio seinan julkisivukuvasta (ajetaan .venv-train:issa).

Nykyiset saannot lukevat sarakkeita kasin kirjoitetulla logiikalla ja
epaonnistuvat reunatapauksissa jotka on mitattu: seinan paassa oleva aukko on
hakualueen ulkopuolella, ja "tyhja sarake" tarkoittaa yhta usein keilausvarjoa
kuin aukkoa. Kumpikin on kontekstikysymys, ja konvoluutio nakee kontekstin.

Malli on 1D-konvoluutio seinan pituussuunnassa: syote on z-profiili
kanavina (48 kaistaa + sarakkeen pistetiheys), ulostulo per sarake
P(aukko). Dilaatiot antavat ~7.5 m nakoalan, eli malli nakee seinan
molemmat puolet aukon ymparilta.

Vertailu ajetaan SAMOISTA ruudukoista kuin saannot (`_op_baseline.py`),
joten ero on menetelmassa eika esikasittelyssa.

Kaytto: .venv-train/Scripts/python _op_train.py <datahakemisto> [--epochs N]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ZB = 48          # z-kaistaa
CROP = 512       # saraketta koulutuskropissa
VAL_SCENES = ("scene_08", "scene_09", "_store_m")
CLEAN = True
NORM = True


def _clean_label(lab, xe, ze, min_w=500.0, min_h=600.0):
    """Poista totuudesta se mita detektori EI edes yrita loytaa.

    Rohbaun aukkoluokissa on runsaasti 544 x 423 mm putkilapivienteja
    katonrajassa; `_MIN_W`/`_MIN_H` hylkaa ne oikein, joten ne eivat kuulu
    nimittajaan. Ilman tata seka verkko etta saannot saavat teennaisen
    matalan kattavuuden samasta syysta."""
    lab = lab.astype(bool).copy()
    cols = lab.any(axis=1)
    out = np.zeros_like(lab)
    s = None
    for i in range(len(cols) + 1):
        v = cols[i] if i < len(cols) else False
        if v and s is None:
            s = i
        elif not v and s is not None:
            w = xe[i] - xe[s]
            rows = lab[s:i].any(axis=0)
            ri = np.flatnonzero(rows)
            h = (ze[ri[-1] + 1] - ze[ri[0]]) if len(ri) else 0.0
            if w >= min_w and h >= min_h:
                out[s:i] = lab[s:i]
            s = None
    return out.astype(np.uint8)


def _features(z) -> tuple[np.ndarray, np.ndarray]:
    occ = z["occ"].astype(np.float32)          # (n_x, n_z)
    n_x, n_z = occ.shape
    edges = np.linspace(0, n_z, ZB + 1).astype(int)
    bands = np.stack([occ[:, edges[i]:edges[i + 1]].mean(axis=1)
                      for i in range(ZB)], axis=0)          # (ZB, n_x)
    if NORM:
        # MiehitysTASO on rakennuksen ominaisuus: Rohbaun rosoinen runko on
        # harva ja myymala tihea, joten tasolla opetettu malli ei siirry
        # rakennuksesta toiseen (mitattu: 0.000 kattavuus molempiin suuntiin).
        # Suhteuta seinan OMAAN mediaaniin — sama saanto kuin muillakin taman
        # putken mittareilla.
        ref = float(np.median(bands[bands > 0])) if (bands > 0).any() else 1.0
        bands = np.clip(bands / max(ref, 1e-3), 0.0, 3.0)
    col = z["col"].astype(np.float32)
    med = float(np.median(col[col > 0])) if (col > 0).any() else 1.0
    col = np.clip(col / max(med, 1e-6), 0.0, 4.0)[None, :]  # (1, n_x)
    x = np.concatenate([bands, col], axis=0).astype(np.float32)
    lab = _clean_label(z["lab"], z["xe"], z["ze"]) if CLEAN else z["lab"]
    y = (lab.astype(np.uint8).any(axis=1)).astype(np.float32)
    return x, y


class Net(nn.Module):
    def __init__(self, cin=ZB + 1, ch=64):
        super().__init__()
        layers, c = [], cin
        for d in (1, 2, 4, 8, 16, 32, 64):
            layers += [nn.Conv1d(c, ch, 5, padding=2 * d, dilation=d),
                       nn.BatchNorm1d(ch), nn.ReLU()]
            c = ch
        self.body = nn.Sequential(*layers)
        self.head = nn.Conv1d(ch, 1, 1)

    def forward(self, x):
        return self.head(self.body(x))[:, 0]


def _load(root: Path, val=None):
    tr, va = [], []
    for f in sorted(root.glob("*.npz")):
        z = dict(np.load(f))
        if "rule" not in z:
            continue
        x, y = _features(z)
        item = {"x": x, "y": y, "rule": z["rule"].astype(np.float32),
                "name": f.stem, "xe": z["xe"]}
        pats = val if val is not None else VAL_SCENES
        (va if any(s in f.stem for s in pats) else tr).append(item)
    return tr, va


def _batch(items, rng, n=16, pos_frac=0.5):
    """Puolet kropeista aukon ympärille.

    Satunnainen kroppi osuu aukkoon harvoin (aukkosarakkeita on ~4 %), joten
    tasainen otanta opettaa mallia lähinnä sanomaan ei. Tämä ei muuta
    validointia — vain sitä mitä malli näkee koulutuksessa."""
    withop = [i for i in items if i["y"].sum() > 0]
    xs, ys = [], []
    for k in range(n):
        want_pos = withop and rng.random() < pos_frac
        it = withop[rng.integers(len(withop))] if want_pos else items[rng.integers(len(items))]
        w = it["x"].shape[1]
        if w <= CROP:
            pad = CROP - w
            xs.append(np.pad(it["x"], ((0, 0), (0, pad))))
            ys.append(np.pad(it["y"], (0, pad), constant_values=-1))
            continue
        if want_pos:
            idx = np.flatnonzero(it["y"] > 0)
            c = int(idx[rng.integers(len(idx))])
            s = int(np.clip(c - CROP // 2 + rng.integers(-80, 80), 0, w - CROP))
        else:
            s = int(rng.integers(w - CROP))
        xs.append(it["x"][:, s:s + CROP])
        ys.append(it["y"][s:s + CROP])
    return torch.from_numpy(np.stack(xs)), torch.from_numpy(np.stack(ys))


def _runs(mask):
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(mask) - 1))
    return out


def _opening_scores(pred, truth, xe, min_mm=500.0):
    """Aukkotason osumat: ennusteen ja totuuden jaksot paallekkain."""
    pr = [r for r in _runs(pred > 0.5) if xe[r[1] + 1] - xe[r[0]] >= min_mm]
    gt = _runs(truth > 0.5)
    hit_gt = sum(any(min(g[1], p[1]) >= max(g[0], p[0]) for p in pr) for g in gt)
    hit_pr = sum(any(min(g[1], p[1]) >= max(g[0], p[0]) for g in gt) for p in pr)
    return hit_gt, len(gt), hit_pr, len(pr)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/_op_data")
    epochs = 400
    if "--epochs" in sys.argv:
        epochs = int(sys.argv[sys.argv.index("--epochs") + 1])
    val = None
    if "--val" in sys.argv:
        val = tuple(sys.argv[sys.argv.index("--val") + 1].split(","))
    tr, va = _load(root, val)
    print(f"koulutus {len(tr)} seinaa, validointi {len(va)} seinaa", flush=True)
    if not tr:
        print("liian vahan dataa"); return

    pos = sum(float(i["y"].sum()) for i in tr)
    neg = sum(float((i["y"] == 0).sum()) for i in tr)
    pw = torch.tensor(max(neg / max(pos, 1.0), 1.0), dtype=torch.float32)
    print(f"aukkosarakkeita {pos:,.0f} / {pos + neg:,.0f}  pos_weight {float(pw):.1f}",
          flush=True)

    torch.manual_seed(0)
    rng = np.random.default_rng(0)
    net = Net()
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    lossf = nn.BCEWithLogitsLoss(pos_weight=pw, reduction="none")
    for ep in range(epochs):
        net.train()
        x, y = _batch(tr, rng)
        out = net(x)
        m = y >= 0
        loss = (lossf(out, y.clamp(min=0)) * m).sum() / m.sum().clamp(min=1)
        opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        if (ep + 1) % 50 == 0:
            print(f"  epookki {ep + 1:4d}  loss {float(loss):.4f}", flush=True)

    net.eval()
    print(f"\n{'seina':26s} {'GT':>3} {'verkko':>12} {'saannot':>12}")
    tot = np.zeros(4, float)
    rtot = np.zeros(4, float)
    preds = {}
    with torch.no_grad():
        for it in va:
            p = torch.sigmoid(net(torch.from_numpy(it["x"][None]))).numpy()[0]
            preds[it["name"]] = p
            a, b, c, d = _opening_scores(p, it["y"], it["xe"])
            ra, rb, rc, rd = _opening_scores(it["rule"], it["y"], it["xe"])
            tot += (a, b, c, d)
            rtot += (ra, rb, rc, rd)
            print(f"{it['name']:26s} {b:3d} {a:5d}/{b:<2d} {c:3d}/{d:<3d} "
                  f"{ra:5d}/{rb:<2d} {rc:3d}/{rd:<3d}")
    print(f"\n{'':26s} {'kattavuus':>10} {'tarkkuus':>10}")
    print(f"{'VERKKO':26s} {tot[0] / max(tot[1], 1):10.3f} {tot[2] / max(tot[3], 1):10.3f}")
    print(f"{'SAANNOT':26s} {rtot[0] / max(rtot[1], 1):10.3f} "
          f"{rtot[2] / max(rtot[3], 1):10.3f}")

    torch.save(net.state_dict(), root / "_op_net.pt")
    np.savez_compressed(root / "_op_pred.npz", **preds)
    dummy = torch.zeros(1, ZB + 1, 1024)
    torch.onnx.export(net, dummy, str(root / "_op_net.onnx"),
                      input_names=["x"], output_names=["logit"],
                      dynamic_axes={"x": {2: "w"}, "logit": {1: "w"}},
                      dynamo=False)
    print(f"\ntallennettu {root / '_op_net.onnx'}")


if __name__ == "__main__":
    main()

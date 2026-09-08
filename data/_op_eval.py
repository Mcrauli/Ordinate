"""Arvioi opittu malli ja saannot samasta datasta (ajetaan .venv-train:issa).

Kaytto: _op_eval.py <datahakemisto> <malli.pt>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _op_train import Net, _features, _opening_scores  # noqa: E402


def main(root: str, ckpt: str) -> None:
    d = Path(root)
    net = Net()
    net.load_state_dict(torch.load(ckpt, map_location="cpu"))
    net.eval()
    tot = np.zeros(4, float)
    rtot = np.zeros(4, float)
    preds = {}
    rows = []
    with torch.no_grad():
        for f in sorted(d.glob("*.npz")):
            if f.name.startswith("_"):
                continue
            z = dict(np.load(f))
            if "rule" not in z or not z["lab"].any():
                continue
            x, y = _features(z)
            p = torch.sigmoid(net(torch.from_numpy(x[None]))).numpy()[0]
            preds[f.stem] = p
            a, b, c, e = _opening_scores(p, y, z["xe"])
            ra, rb, rc, rd = _opening_scores(z["rule"].astype(float), y, z["xe"])
            tot += (a, b, c, e)
            rtot += (ra, rb, rc, rd)
            rows.append((f.stem, b, a, c, e, ra, rc, rd))
    print(f"{'seina':28s} {'GT':>3} {'verkko loyt/ennus':>18} {'saannot loyt/ennus':>19}")
    for n, b, a, c, e, ra, rc, rd in rows:
        print(f"{n:28s} {b:3d} {a:8d}/{b:<3d} {c:3d}/{e:<3d} {ra:8d}/{b:<3d} {rc:3d}/{rd:<3d}")
    print(f"\n{'':28s} {'kattavuus':>10} {'tarkkuus':>10}")
    print(f"{'VERKKO':28s} {tot[0] / max(tot[1], 1):10.3f} {tot[2] / max(tot[3], 1):10.3f}")
    print(f"{'SAANNOT':28s} {rtot[0] / max(rtot[1], 1):10.3f} "
          f"{rtot[2] / max(rtot[3], 1):10.3f}")
    np.savez_compressed(d / "_op_pred.npz", **preds)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

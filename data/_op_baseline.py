"""Nykyisten SAANTOJEN ennuste samoista ruudukoista kuin verkolle.

Vertailu on patevaa vain jos molemmat saavat saman syotteen. `_op_dataset.py`
tallensi tuotannon oman ruudukon; tama ajaa siihen `_find_openings`in ja
kirjoittaa sarakemaskin samaan tiedostoon, jolloin `_op_train.py` voi verrata
verkkoa ja saantoja rivi riviltta.

Kaytto: _op_baseline.py <datahakemisto>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scan2bim.core.segmentation import opening_detector as OD  # noqa: E402
from scan2bim.schemas.model import ElementSource, Wall  # noqa: E402


def main(root: str) -> None:
    d = Path(root)
    files = sorted(d.glob("*.npz"))
    done = 0
    for f in files:
        z = dict(np.load(f))
        if "rule" in z:
            done += 1
            continue
        occ = z["occ"].astype(bool)
        xe, ze = z["xe"], z["ze"]
        L, th, z0, h = z["meta"]
        a0, a1 = z["anchors"]
        w = Wall(id=f.stem[-6:], confidence=1.0, classification="wall",
                 source=ElementSource(method="manual"),
                 axis=[[0.0, 0.0], [float(L), 0.0]], height=float(h),
                 thickness=float(th), z_min=float(z0))
        ops = OD._find_openings(occ, z["col"].astype(float), xe, ze,
                                occ.shape[0], occ.shape[1], float(L), w,
                                float(z0), 0, bool(a0), bool(a1))
        mask = np.zeros(occ.shape[0], np.uint8)
        xc = 0.5 * (xe[:-1] + xe[1:])
        for op in ops:
            s = float(op.position_along)
            mask[(xc >= s) & (xc <= s + float(op.width))] = 1
        z["rule"] = mask
        np.savez_compressed(f, **z)
        done += 1
    print(f"saantojen ennuste {done}/{len(files)} tiedostoon")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/_op_data")

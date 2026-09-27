"""EKVIVALENSSI: suodattimen tulos ennen/jalkeen muutoksen, bitilleen.

Muistikorjaus saa muuttaa vain sita PALJONKO muistia kuluu, ei sita mita
suodatin paattaa. Tama tiivistaa suodatuksen koko tuloksen (pidetyt pisteet +
semanttiset labelit) tarkistussummiksi, jotka voi verrata git stashin yli.

Aja:  .venv\\Scripts\\python data/_filter_equiv.py data/_cache_apt.ply uusi.json
      git stash push -- src/  &&  ... vanha.json  &&  git stash pop
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def _h(a: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(a)).hexdigest()[:16]


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])

    from ordinate.core.geometry.loader import load_point_cloud
    from ordinate.core.segmentation.pointnet_filter import PointNetFilter

    cloud = load_point_cloud(src)
    n_in = len(cloud.points)
    filt = PointNetFilter()
    assert filt.is_available(), "ONNX-mallia ei loydy — vertailu ei kelpaa"

    kept, labels = filt.filter_with_labels(cloud)
    kp = np.asarray(kept.points)

    rec = {
        "cloud": src.name,
        "n_in": n_in,
        "n_kept": len(kp),
        "kept_xyz": _h(kp.astype(np.float64)),
        "labels": None if labels is None else {
            "n_keys": int(len(labels._keys)),
            "keys": _h(labels._keys),
            "values": _h(labels._labels),
            "origin": [round(float(v), 6) for v in labels._origin],
        },
    }
    # predict_classes on erillinen julkinen polku — sekin pysyttava samana
    pred = filt.predict_classes(np.asarray(cloud.points))
    rec["pred"] = None if pred is None else {
        "n": int(len(pred)), "hash": _h(pred.astype(np.int64)),
        "bincount": np.bincount(pred + 1, minlength=14).tolist(),
    }

    out.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()

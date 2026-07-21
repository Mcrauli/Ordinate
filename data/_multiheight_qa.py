"""Monikorkeus-stressitesti labeloidulla synteettisella datalla.

Rohbaussa on vain yksi monikorkea skene. Tama kattaa kayttajan painottamat
tapaukset eksplisiittisesti, GT-labelein → tarkka rakenne-saily / krassa-poisto:
  1. korkea varasto (8 m katto, korkea hylly, korkea palkki)
  2. kaksikerroksinen (valilattia 3 m, palkki valikorkeudella, portaat)
  3. erilliset eri korkuiset huoneet (2.6 m + 4.5 m vierekkain)

Vertaa tuotantoa ja ehdokasta samalla inferenssipolulla.

Aja (.venv):
  python data/_multiheight_qa.py --model models/_new/bench/pointnet_geocol_v2_retail.onnx
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scan2bim.core.segmentation.pointnet_filter import PointNetFilter, _slab_bands

REPO = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(2027)

# label: 1=rakenne (seina/lattia/katto/palkki/pilari/porras), 0=krassa (poista)
STRUCT, CLUT = 1, 0


def _plane_z(x0, x1, y0, y1, z, n, surf=0.01):
    return np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n),
                            z + rng.normal(0, surf, n)])


def _plane_x(x, y0, y1, z0, z1, n, surf=0.01):
    return np.column_stack([np.full(n, x) + rng.normal(0, surf, n),
                            rng.uniform(y0, y1, n), rng.uniform(z0, z1, n)])


def _plane_y(y, x0, x1, z0, z1, n, surf=0.01):
    return np.column_stack([rng.uniform(x0, x1, n), np.full(n, y) + rng.normal(0, surf, n),
                            rng.uniform(z0, z1, n)])


def _emit(parts, labels, p, lab):
    parts.append(p); labels.append(np.full(len(p), lab))


def warehouse(W=12.0, D=10.0, H=8.0):
    """Korkea varasto: 8 m katto, korkea palkki 6 m, korkea hylly, tavaraa."""
    P, L = [], []
    _emit(P, L, _plane_z(0, W, 0, D, 0.0, 12000), STRUCT)          # lattia
    _emit(P, L, _plane_z(0, W, 0, D, H, 12000), STRUCT)            # katto (korkea)
    for x in (0.0, W):
        _emit(P, L, _plane_x(x, 0, D, 0, H, 9000), STRUCT)        # korkeat seinat
    for y in (0.0, D):
        _emit(P, L, _plane_y(y, 0, W, 0, H, 9000), STRUCT)
    _emit(P, L, _plane_z(2, W - 2, D / 2 - 0.15, D / 2 + 0.15, 6.0, 3000), STRUCT)  # korkea palkki 6 m
    # korkea hylly (kaluste, poista) x=3, 0-5 m
    _emit(P, L, _plane_x(3.0, 1, D - 1, 0, 5.0, 4000, surf=0.02), CLUT)
    _emit(P, L, rng.uniform([5, 1, 0], [9, D - 1, 1.5], size=(4000, 3)), CLUT)      # lattiatavara
    return np.vstack(P), np.concatenate(L)


def twostory(W=8.0, D=7.0):
    """Kaksikerroksinen: valilattia 3 m, palkki 2.8 m (valikorkeus), portaat."""
    P, L = [], []
    _emit(P, L, _plane_z(0, W, 0, D, 0.0, 9000), STRUCT)          # lattia L1
    _emit(P, L, _plane_z(0, W, 0, D, 3.0, 9000), STRUCT)          # valilattia
    _emit(P, L, _plane_z(0, W, 0, D, 6.0, 9000), STRUCT)          # katto
    for x in (0.0, W):
        _emit(P, L, _plane_x(x, 0, D, 0, 6.0, 12000), STRUCT)
    for y in (0.0, D):
        _emit(P, L, _plane_y(y, 0, W, 0, 6.0, 12000), STRUCT)
    _emit(P, L, _plane_z(1, W - 1, 1.0, 1.3, 2.8, 3000), STRUCT)  # palkki VALIKORKEUS 2.8 m
    # portaat: nouseva ramppi L1->L2
    t = rng.uniform(0, 1, 5000)
    _emit(P, L, np.column_stack([1 + t * 3, np.full(5000, D - 1) + rng.normal(0, 0.05, 5000),
                                 t * 3 + rng.normal(0, 0.03, 5000)]), STRUCT)
    _emit(P, L, rng.uniform([2, 2, 0], [4, 4, 0.8], size=(2500, 3)), CLUT)          # poyta L1
    _emit(P, L, rng.uniform([2, 2, 3.0], [4, 4, 3.8], size=(2500, 3)), CLUT)        # poyta L2
    return np.vstack(P), np.concatenate(L)


def splitrooms():
    """Kaksi vierekkaista eri korkuista huonetta: 2.6 m ja 4.5 m."""
    P, L = [], []
    # huone A: x 0-5, katto 2.6
    _emit(P, L, _plane_z(0, 5, 0, 5, 0.0, 8000), STRUCT)
    _emit(P, L, _plane_z(0, 5, 0, 5, 2.6, 8000), STRUCT)
    for x in (0.0, 5.0):
        _emit(P, L, _plane_x(x, 0, 5, 0, 2.6, 6000), STRUCT)
    # huone B: x 5-10, katto 4.5 (korkeampi)
    _emit(P, L, _plane_z(5, 10, 0, 5, 0.0, 8000), STRUCT)
    _emit(P, L, _plane_z(5, 10, 0, 5, 4.5, 8000), STRUCT)
    for x in (5.0, 10.0):
        _emit(P, L, _plane_x(x, 0, 5, 0, 4.5, 8000), STRUCT)
    for y in (0.0, 5.0):
        _emit(P, L, _plane_y(y, 0, 10, 0, 4.5, 9000), STRUCT)
    _emit(P, L, rng.uniform([1, 1, 0], [2, 2, 0.8], size=(2500, 3)), CLUT)
    _emit(P, L, rng.uniform([6, 1, 0], [8, 3, 1.6], size=(3000, 3)), CLUT)          # korkea kaappi hB
    return np.vstack(P), np.concatenate(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="")
    a = ap.parse_args()
    scenes = [("korkea varasto 8m", warehouse()), ("kaksikerroksinen", twostory()),
              ("erikorkuiset huoneet", splitrooms())]
    models = [("TUOTANTO", REPO / "models" / "s3dis_pointnet.onnx")]
    if a.model:
        models.append(("EHDOKAS", Path(a.model)))
    for mtag, mp in models:
        filt = PointNetFilter(model_path=mp)
        print(f"\n########## {mtag} (piirteita={getattr(filt,'_n_features','?')}) ##########", flush=True)
        for name, (xyz, lbl) in scenes:
            xyz_mm = xyz.astype(np.float64) * 1000.0
            keep = filt._classify(xyz_mm) | _slab_bands(xyz_mm)
            sk = keep[lbl == STRUCT].mean()
            rr = (~keep[lbl == CLUT]).mean()
            print(f"  {name:22s} rakenne-saily={sk:.3f}  krassa-poisto={rr:.3f}", flush=True)


if __name__ == "__main__":
    main()

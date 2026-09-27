"""Nopeutuuko PointNet INT8-kvantisoinnilla — ja muuttuvatko luokat?

Inferenssi on 405 s / 801 s = 51 % kellarin TUOTANTOajosta (kehitysvalimuisti
pois). Saikeiden lisaaminen mitattiin jo hyodyttomaksi (8 saietta 4.70 s,
16 saietta 4.92 s), joten ainoa jaljella oleva vipu joka ei muuta ketjua on
malli itse.

`onnxruntime.quantization.quantize_dynamic` on osa jo asennettua
onnxruntimea (Apache-2.0) — ei uutta riippuvuutta eika lisenssialtistusta.

MUTTA INT8 EI OLE ILMAINEN: se muuttaa lukuja. Piste jonka kaksi luokkaa ovat
lahella toisiaan voi vaihtaa luokkaa, ja semanttinen suodatin poistaa pisteita
sen perusteella. Siksi tama mittaa KOLME asiaa eika yhta:

  1. nopeus
  2. logittien suurin ero
  3. **argmaxin muutos** — montako pistetta vaihtaa luokkaa

Vasta jos 3 on nolla tai hyvin pieni, muutosta voi harkita — ja silloinkin
matriisi ratkaisee.

Kaytto: _quant_probe.py [erien_maara]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _session(model_path: str, threads: int = 8):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = threads
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(model_path, sess_options=opts,
                                providers=["CPUExecutionProvider"])


def main(n_batches: str = "4") -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    from ordinate.core.segmentation import pointnet_filter as PF

    src = PF._find_model_path()
    if src is None:
        print("ONNX-mallia ei loytynyt")
        return
    src = str(src)
    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = str(out_dir / "_pointnet_int8.onnx")

    print(f"malli: {src}")
    t0 = time.time()
    quantize_dynamic(src, dst, weight_type=QuantType.QInt8)
    print(f"kvantisointi {time.time() - t0:.1f} s  "
          f"koko {Path(src).stat().st_size/1e6:.1f} MB -> "
          f"{Path(dst).stat().st_size/1e6:.1f} MB")

    nb = int(n_batches)
    ref_sess = _session(src)
    inp = ref_sess.get_inputs()[0].name
    nfeat = PF._session_n_features(ref_sess)
    rng = np.random.default_rng(9)
    batches = [rng.random((PF._INFER_BATCH, PF._N_BLOCK_PTS, int(nfeat)),
                          dtype=np.float32) for _ in range(nb)]

    t0 = time.time()
    ref = np.concatenate([ref_sess.run(None, {inp: b})[0] for b in batches], axis=0)
    t_ref = time.time() - t0
    del ref_sess

    q_sess = _session(dst)
    t0 = time.time()
    got = np.concatenate([q_sess.run(None, {inp: b})[0] for b in batches], axis=0)
    t_q = time.time() - t0
    del q_sess

    a, b = ref.argmax(-1), got.argmax(-1)
    changed = float((a != b).mean())
    print(f"\nfloat32: {t_ref:6.2f} s   INT8: {t_q:6.2f} s   "
          f"nopeutus {t_ref / t_q:.2f}x")
    print(f"logittien suurin ero {float(np.abs(ref - got).max()):.4f}")
    print(f"LUOKKA VAIHTUI {changed*100:.2f} % pisteista "
          f"({int((a != b).sum()):,} / {a.size:,})")
    if changed == 0.0:
        print("  -> tulos identtinen; matriisi ratkaisee kelpaako")
    else:
        print("  -> tulos MUUTTUU; ei saa ottaa kayttoon pelkan nopeuden takia")


if __name__ == "__main__":
    main(*sys.argv[1:])

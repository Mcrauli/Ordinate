"""Kannattaako PointNetille antaa enemman sailieta — ja muuttuuko tulos?

PointNet-inferenssi on 405 s / 801 s = 51 % kellarin tuotantoajosta.
`pointnet_filter.py` rajaa `intra_op_num_threads = min(cpu_count, 8)`, ja
koneessa on 16 ydinta. Puolet seisoo.

MUTTA: saikeiden maara voi muuttaa liukulukusummauksen JARJESTYSTA, ja
argmax voi kaantya kun kaksi luokkaa ovat lahella toisiaan. Siksi tata ei saa
muuttaa nopeuden takia ennen kuin on mitattu ETTA TULOS ON SAMA — ei
"kutakuinkin sama", vaan bitilleen.

Tama ajaa saman syotteen lapi eri saiemaarilla ja vertaa (a) logitit
bitilleen, (b) argmaxin. Syote on satunnainen mutta kiinteasiemeninen ja
saman muotoinen kuin tuotannossa (B, 4096, n_features).

Kaytto: _ort_threads_probe.py [erien_maara]
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _session(model_path: str, threads: int):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 1
    opts.intra_op_num_threads = threads
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(model_path, sess_options=opts,
                                providers=["CPUExecutionProvider"])


def main(n_batches: str = "3") -> None:
    from ordinate.core.segmentation import pointnet_filter as PF

    mp = None
    for attr in ("_model_path", "MODEL_PATH", "_MODEL_PATH"):
        mp = getattr(PF, attr, None)
        if mp:
            break
    if mp is None:
        cands = sorted(Path("src").rglob("*.onnx")) + sorted(Path("models").rglob("*.onnx")) \
            + sorted(Path(".").rglob("*.onnx"))
        if not cands:
            print("ONNX-mallia ei loytynyt")
            return
        mp = cands[0]
    mp = str(mp)
    print(f"malli: {mp}")

    nb = int(n_batches)
    probe = _session(mp, 8)
    inp_name = probe.get_inputs()[0].name
    shape = probe.get_inputs()[0].shape
    nfeat = shape[-1] if isinstance(shape[-1], int) else PF._n_features_default \
        if hasattr(PF, "_n_features_default") else 9
    rng = np.random.default_rng(4)
    batches = [rng.random((PF._INFER_BATCH, PF._N_BLOCK_PTS, int(nfeat)),
                          dtype=np.float32) for _ in range(nb)]
    del probe

    ref = None
    for threads in (8, 12, 16):
        sess = _session(mp, threads)
        t0 = time.time()
        outs = [sess.run(None, {inp_name: b})[0] for b in batches]
        dt = time.time() - t0
        out = np.concatenate(outs, axis=0)
        if ref is None:
            ref = out
            same = "(viite)"
        else:
            bit = bool(np.array_equal(ref, out))
            arg = bool(np.array_equal(ref.argmax(-1), out.argmax(-1)))
            mx = float(np.abs(ref - out).max())
            same = f"bitilleen sama: {bit}  argmax sama: {arg}  suurin ero {mx:.3e}"
        print(f"  {threads:2d} saietta: {dt:6.2f} s  ({nb} eraa)  {same}")
        del sess


if __name__ == "__main__":
    main(*sys.argv[1:])

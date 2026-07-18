"""CPU-nopeusmittaus semanttiselle suodattimelle: kelpaako DGCNN+geo exeen?

Mittaa erikseen (1) geo-piirteiden laskennan, (2) ONNX-inferenssin CPU:lla, ja
vertaa tuotannon PointNetiin. Tulos skaalataan realistiseen pilveen, jotta
nähdään minuutteina mitä vaihto maksaisi asiakkaan koneella.

Aja (.venv_train tai .venv):
  python bench_semantic_cpu.py --pth models/_new/dgcnn_geo_3dses.pth --blocks 32
"""
import sys, time, argparse
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
def _imp(n, p):
    s = importlib.util.spec_from_file_location(n, str(Path(__file__).parent / p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
E = _imp("exp", "export_s3dis_model.py")
GEO = _imp("geo", "geo_feats.py")

N_PTS = 4096


def _export(pth, out_onnx, arch, in_ch):
    """Vie ONNXiin. HUOM: ei käytä E.export_onnx:ää — se kovakoodaa 9 kanavaa ja
    kirjoittaa .pth:n samalla nimirungolla (ylikirjoitusriski)."""
    import torch
    builders = {"dgcnn": E._build_dgcnn, "pointnet": E._build_model}
    ck = torch.load(pth, map_location="cpu")
    in_ch = ck.get("in_ch", in_ch)
    model = builders[arch](13, in_ch); model.load_state_dict(ck["model_state_dict"]); model.eval()
    out_onnx.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, N_PTS, in_ch)
    torch.onnx.export(model, dummy, str(out_onnx), input_names=["input"], output_names=["output"],
                      dynamic_axes={"input": {0: "B"}, "output": {0: "B"}}, opset_version=17, dynamo=False)
    print(f"  viety {out_onnx.name} ({out_onnx.stat().st_size//1024} KB, in_ch={in_ch})", flush=True)
    return in_ch


def _bench_onnx(path, in_ch, n_blocks, threads):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    x = np.random.rand(1, N_PTS, in_ch).astype(np.float32)
    for _ in range(3):                                  # lämmittely
        sess.run(None, {name: x})
    t0 = time.perf_counter()
    for _ in range(n_blocks):
        sess.run(None, {name: x})
    dt = time.perf_counter() - t0
    return dt / n_blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pth", default="models/_new/dgcnn_geo_3dses.pth")
    ap.add_argument("--prod-onnx", default="models/s3dis_pointnet.onnx")
    ap.add_argument("--blocks", type=int, default=32)
    ap.add_argument("--threads", type=int, default=4, help="asiakaskoneen realistinen ydinmäärä")
    ap.add_argument("--cloud-pts", type=int, default=5_000_000, help="realistinen pilvi harvennuksen jälkeen")
    ap.add_argument("--skip-export", action="store_true", help="käytä jo vietyä ONNXia (esim. ajo ilman torchia)")
    a = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = root / "models" / "_new" / "bench" / "dgcnn_geo.onnx"
    print("=== ONNX-vienti (DGCNN+geo) ===", flush=True)
    try:
        if a.skip_export and out.exists():
            in_ch = 13
            print(f"  ohitettu, käytetään {out.name}", flush=True)
        else:
            in_ch = _export(root / a.pth, out, "dgcnn", 13)
    except Exception as e:
        print(f"  VIENTI KAATUI: {type(e).__name__}: {e}", flush=True)
        print("  -> DGCNN ei mene ONNXiin nykyisellä exportilla; tuotantopolku katkeaa tähän.", flush=True)
        return

    print(f"\n=== CPU-inferenssi ({a.threads} säiettä) ===", flush=True)
    t_new = _bench_onnx(out, in_ch, a.blocks, a.threads)
    print(f"  DGCNN+geo : {t_new*1000:8.1f} ms/lohko", flush=True)

    prod = root / a.prod_onnx
    t_old = None
    if prod.exists():
        import onnxruntime as ort
        pin = ort.InferenceSession(str(prod), providers=["CPUExecutionProvider"]).get_inputs()[0]
        prod_ch = pin.shape[-1] if isinstance(pin.shape[-1], int) else 9
        t_old = _bench_onnx(prod, prod_ch, a.blocks, a.threads)
        print(f"  PointNet  : {t_old*1000:8.1f} ms/lohko  (tuotanto, in_ch={prod_ch})", flush=True)
        print(f"  suhde     : {t_new/t_old:8.1f}x hitaampi", flush=True)

    print("\n=== geo-piirteiden laskenta (cKDTree) ===", flush=True)
    for n in (200_000, 1_000_000):
        pts = np.random.rand(n, 3).astype(np.float32) * 10
        t0 = time.perf_counter(); GEO.compute(pts); dt = time.perf_counter() - t0
        print(f"  {n:>9,} pistettä: {dt:6.2f} s  ({n/dt/1e6:.2f} M pistettä/s)", flush=True)

    # Lohkomäärän ajaa LATTIA-ALA, ei pistemäärä: pointnet_filter ajaa 30 mm
    # työ-voxelilla, 1 m lohkot 0.5 m stridellä -> ~4 lohkoa / m2.
    print("\n=== skaalaus lattia-alan mukaan (~4 lohkoa/m2) ===", flush=True)
    print(f"  {'kohde':<28}{'lohkoja':>9}{'DGCNN+geo':>12}{'PointNet':>11}", flush=True)
    for name, area in [("asunto 100 m2", 100), ("talo 350 m2", 350),
                       ("Radikal-myymala 3000 m2", 3000)]:
        nb = int(area * 4)
        old = f"{nb*t_old/60:8.1f} min" if t_old else "        -"
        print(f"  {name:<28}{nb:>9,}{nb*t_new/60:9.1f} min{old:>11}", flush=True)


if __name__ == "__main__":
    main()

"""Export a trained .pth (with in_ch in checkpoint) to ONNX at the correct width.

The stock export_s3dis_model.export_onnx hardcodes a 9-channel dummy and also
overwrites out.with_suffix('.pth') — this helper avoids both: reads in_ch from
the checkpoint, builds the model at that width, and writes ONLY the .onnx.

  python export_pth_onnx.py <in.pth> <out.onnx>
"""
import sys
import importlib.util
from pathlib import Path

import torch


def _imp(name, rel):
    p = str(Path(__file__).resolve().parent / rel)
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main():
    E = _imp("exp", "export_s3dis_model.py")
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    ck = torch.load(str(src), map_location="cpu")
    in_ch = int(ck.get("in_ch", 13)) if isinstance(ck, dict) else 13
    state = ck.get("model_state_dict", ck) if isinstance(ck, dict) else ck
    model = E._build_model(k=13, in_ch=in_ch)
    model.load_state_dict(state, strict=True)
    model.eval()
    out.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, 4096, in_ch)
    torch.onnx.export(
        model, dummy, str(out),
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {0: "B", 1: "N"}, "output": {0: "B", 1: "N"}},
        opset_version=17, dynamo=False,
    )
    print(f"exported {out} in_ch={in_ch} {out.stat().st_size // 1024} KB", flush=True)


if __name__ == "__main__":
    main()

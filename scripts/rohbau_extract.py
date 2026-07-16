"""Pura Rohbau3D site_XX.{attr}.partNNN.tar.zst -> scenes/scene_XXXXX/{attr}.npy."""
import sys, tarfile, io, re
from pathlib import Path
import zstandard as zstd

def extract(src_dir: Path, out_dir: Path, sites, attrs):
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(src_dir.glob("site_*.tar.zst"))
    dctx = zstd.ZstdDecompressor()
    done = 0
    for f in files:
        m = re.match(r"site_(\d+)\.(\w+)\.part\d+\.tar\.zst", f.name)
        if not m: continue
        s, attr = int(m.group(1)), m.group(2)
        if (sites and s not in sites) or (attrs and attr not in attrs): continue
        print(f"  purkaa {f.name}…", flush=True)
        with open(f, "rb") as fh:
            with dctx.stream_reader(fh) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    tar.extractall(out_dir, filter="data")
        done += 1
    print(f"Purettu {done} arkistoa -> {out_dir}", flush=True)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--sites", default=""); ap.add_argument("--attrs", default="coord,intensity,color,class")
    a = ap.parse_args()
    sites = {int(x) for x in a.sites.split(",") if x.strip()!=""}
    attrs = set(a.attrs.split(","))
    extract(Path(a.src), Path(a.out), sites, attrs)

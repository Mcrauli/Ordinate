"""Aja koulutettu semanttinen suodatin OIKEALLA kalustepilvellä (S170/S171) ja
näytä visionilla: poistaako se kalusteet (valepilarien lähde) säilyttäen seinät.
Rehellinen yleistystesti (koulutus Rohbau+synteettinen, testi oikea 3DSES-kaluste).

Piirteet 10: xyz_local + xyz_scene + rgb + korkeus (sama kuin --no-intensity-malli).

Aja (.venv_train):
  python test_filter_on_scan.py --ply PATH --model models/_new/combined_rgbh.pth --out img.png
"""
import sys, argparse
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
_s = importlib.util.spec_from_file_location("exp", str(Path(__file__).parent / "export_s3dis_model.py"))
E = importlib.util.module_from_spec(_s); _s.loader.exec_module(E)

_KEEP = {0, 1, 2, 3, 4, 5, 6}
_BLOCK, _STRIDE, _NPTS = 1.0, 0.5, 4096


def classify(pts, extra, model, device):
    """Sliding-block äänestys → per-piste rakenne-maski (True=säilytä)."""
    import torch
    sc_min = pts.min(0); sc_range = np.maximum(pts.max(0) - sc_min, 1e-6)
    xs = np.arange(sc_min[0], pts[:, 0].max() - _BLOCK + 1e-6, _STRIDE)
    ys = np.arange(sc_min[1], pts[:, 1].max() - _BLOCK + 1e-6, _STRIDE)
    votes = np.zeros((len(pts), 13), np.float32)
    cellx = np.floor((pts[:, 0] - sc_min[0]) / _STRIDE).astype(np.int64)
    celly = np.floor((pts[:, 1] - sc_min[1]) / _STRIDE).astype(np.int64)
    ncy = int(celly.max()) + 2
    ckey = cellx * ncy + celly; order = np.argsort(ckey, kind="stable")
    uniq, starts = np.unique(ckey[order], return_index=True)
    ends = np.append(starts[1:], len(order))
    cmap = {int(u): order[s:e] for u, s, e in zip(uniq, starts, ends)}
    model.eval()
    with torch.no_grad():
        for bi, cx in enumerate(xs):
            for bj, cy in enumerate(ys):
                cand = [cmap[k] for k in (bi*ncy+bj, bi*ncy+bj+1, (bi+1)*ncy+bj, (bi+1)*ncy+bj+1) if k in cmap]
                if not cand: continue
                cidx = np.concatenate(cand); sub = pts[cidx]
                m = (sub[:,0]>=cx)&(sub[:,0]<cx+_BLOCK)&(sub[:,1]>=cy)&(sub[:,1]<cy+_BLOCK)
                idx = cidx[m]
                if len(idx) < 32: continue
                sel = (np.random.choice(len(idx), _NPTS, replace=False) if len(idx) >= _NPTS
                       else np.concatenate([np.arange(len(idx)), np.random.choice(len(idx), _NPTS-len(idx))]))
                picked = idx[sel]; s = pts[picked]
                f = np.zeros((_NPTS, 6 + extra.shape[1]), np.float32)
                f[:,0]=(s[:,0]-cx)/_BLOCK; f[:,1]=(s[:,1]-cy)/_BLOCK; f[:,2]=(s[:,2]-sc_min[2])/sc_range[2]
                f[:,3]=(s[:,0]-sc_min[0])/sc_range[0]; f[:,4]=(s[:,1]-sc_min[1])/sc_range[1]; f[:,5]=(s[:,2]-sc_min[2])/sc_range[2]
                f[:,6:]=extra[picked]
                logits = model(torch.tensor(f[None]).to(device))[0].cpu().numpy()
                pred = logits.argmax(-1)
                probs = np.zeros((_NPTS,13),np.float32); probs[np.arange(_NPTS),pred]=1.0
                np.add.at(votes, picked, probs)
    no_vote = votes.sum(1) == 0
    keep = np.isin(votes.argmax(1), list(_KEEP)); keep[no_vote] = True
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ply", required=True); ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--voxel", type=float, default=0.03)
    ap.add_argument("--save-dir", default="")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt = torch.load(a.model, map_location=device, weights_only=True)
    in_ch = ckpt.get("in_ch", 10)
    model = E._build_model(13, in_ch).to(device)
    model.load_state_dict(ckpt["model_state_dict"]); print(f"malli {a.model} in_ch={in_ch} device={device}", flush=True)

    pts_full, rgb_full = _read_ply(a.ply)
    pts_full = pts_full.astype(np.float32)
    rgb_full = (rgb_full.astype(np.float32) / 255.0) if rgb_full is not None else np.full((len(pts_full),3), 0.5, np.float32)
    span = pts_full.max(0)-pts_full.min(0)
    if span.max() > 200: pts_full = pts_full/1000.0
    # voxel-edustajat luokitteluun; PÄÄTÖS peritään takaisin TÄYSILLE pisteille
    k = np.floor(pts_full / a.voxel).astype(np.int64)
    key1d = k[:,0]*10_000_000 + k[:,1]*1_000 + k[:,2]
    uniq, first_idx, inverse = np.unique(key1d, return_index=True, return_inverse=True)
    pts, rgb = pts_full[first_idx], rgb_full[first_idx]
    floor_z = np.percentile(pts[:,2], 2)
    height = np.clip((pts[:,2]-floor_z)/3.0, 0, 1.5)
    extra = np.column_stack([rgb, height]).astype(np.float32)   # 4 -> 10 feat
    print(f"täysiä {len(pts_full):,} | voxel-edustajia {len(pts):,} ({a.voxel}m)", flush=True)

    keep_ds = classify(pts, extra, model, device)
    keep_full = keep_ds[inverse]                                # täysres-maski
    print(f"==> TÄYSRES säilytetty {100*keep_full.mean():.1f}% | poistettu {100*(~keep_full).mean():.1f}%", flush=True)

    if a.save_dir:
        sd = Path(a.save_dir); sd.mkdir(parents=True, exist_ok=True)
        stem = Path(a.ply).stem
        rgb255f = np.clip(rgb_full * 255, 0, 255).astype(np.uint8)
        _write_ply(sd / f"{stem}_all.ply", pts_full, rgb255f)
        _write_ply(sd / f"{stem}_filt.ply", pts_full[keep_full], rgb255f[keep_full])
        print(f"tallennettu (täysres): {stem}_all.ply ({len(pts_full)}) + {stem}_filt.ply ({int(keep_full.sum())})", flush=True)

    keep = keep_ds
    # vision: ylhäältä, säilytetty harmaa / poistettu punainen
    sub = np.random.default_rng(0).choice(len(pts), min(300000,len(pts)), replace=False)
    fig, ax = plt.subplots(figsize=(11,9))
    ax.scatter(pts[sub][keep[sub],0], pts[sub][keep[sub],1], s=0.4, c="0.6", lw=0, label="säilytetty")
    ax.scatter(pts[sub][~keep[sub],0], pts[sub][~keep[sub],1], s=0.6, c="red", lw=0, label="poistettu (kaluste?)")
    ax.set_aspect("equal"); ax.legend(); ax.set_title(f"{Path(a.ply).stem}: suodatin (poistettu punainen)")
    fig.savefig(a.out, dpi=85, bbox_inches="tight"); print(f"kuva {a.out}", flush=True)


_PLY_NP = {b"double":"<f8", b"float":"<f4", b"float32":"<f4", b"float64":"<f8",
           b"uchar":"u1", b"uint8":"u1", b"int":"<i4", b"uint":"<u4",
           b"ushort":"<u2", b"short":"<i2"}


def _read_ply(path):
    """Binääri-PLY (xyz + valinnainen rgb) numpyllä — ei open3d-riippuvuutta."""
    with open(path, "rb") as f:
        head = b""
        while b"end_header" not in head:
            head += f.read(256)
        hdr_end = head.index(b"end_header") + len(b"end_header") + 1
        f.seek(hdr_end)
        lines = head[:hdr_end].split(b"\n")
        count = 0; fields = []
        for ln in lines:
            t = ln.split()
            if len(t) >= 3 and t[0] == b"element" and t[1] == b"vertex":
                count = int(t[2])
            elif len(t) == 3 and t[0] == b"property":
                fields.append((t[2].decode(), _PLY_NP.get(t[1], "<f8")))
        dt = np.dtype(fields)
        arr = np.frombuffer(f.read(count * dt.itemsize), dtype=dt, count=count)
    pts = np.column_stack([arr["x"], arr["y"], arr["z"]]).astype(np.float64)
    rgb = None
    if all(c in arr.dtype.names for c in ("red", "green", "blue")):
        rgb = np.column_stack([arr["red"], arr["green"], arr["blue"]])
    return pts, rgb


def _write_ply(path, pts, rgb):
    """Binääri-PLY (double xyz + uchar rgb) metreissä."""
    n = len(pts)
    hdr = ("ply\nformat binary_little_endian 1.0\n"
           f"element vertex {n}\n"
           "property double x\nproperty double y\nproperty double z\n"
           "property uchar red\nproperty uchar green\nproperty uchar blue\n"
           "end_header\n").encode()
    dt = np.dtype([("x","<f8"),("y","<f8"),("z","<f8"),("r","u1"),("g","u1"),("b","u1")])
    arr = np.empty(n, dt)
    arr["x"], arr["y"], arr["z"] = pts[:,0], pts[:,1], pts[:,2]
    arr["r"], arr["g"], arr["b"] = rgb[:,0], rgb[:,1], rgb[:,2]
    with open(path, "wb") as f:
        f.write(hdr); f.write(arr.tobytes())


def _voxel_repr_idx(pts, voxel_m):
    keys = np.floor(pts / voxel_m).astype(np.int64)
    k1 = keys[:,0]*10_000_000 + keys[:,1]*1_000 + keys[:,2]
    order = np.argsort(k1, kind="stable"); _, first = np.unique(k1[order], return_index=True)
    return order[first]


if __name__ == "__main__":
    main()

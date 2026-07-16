"""Yhdistetty koulutus: Rohbau (oikea runko, rikkaat piirteet) + oma synteettinen
kalustedata (täyskorkeat kaapit ym. = kaluste). Opettaa erottamaan aidon pilarin
(Rohbau, säilytä) täyskorkeasta kaapista (synteettinen, poista) VÄRIN/INTENSITEETIN
avulla — geometria yksin ei riitä. License-puhdas (Rohbau CC-BY + oma synteettinen).

Piirteet: xyz_local + xyz_scene + rgb + intensiteetti + korkeus (11), sama kuin
de-risk. Held-out: Rohbau-työmaa (rakenne) + synteettinen (kaluste-poisto).

Aja (.venv_train):
  python rohbau_synth_combined.py --root DIR --train 1,4,13 --val 7,10 --synth 40 --epochs 20
"""
import sys, glob, time, argparse
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
_s = importlib.util.spec_from_file_location("exp", str(Path(__file__).parent / "export_s3dis_model.py"))
E = importlib.util.module_from_spec(_s); _s.loader.exec_module(E)
_s2 = importlib.util.spec_from_file_location("fx", str(Path(__file__).parent / "rohbau_feature_exp.py"))
FX = importlib.util.module_from_spec(_s2); _s2.loader.exec_module(FX)

_RM = [7, 8, 9, 10, 11, 12]

# per-luokka ulkonäkö (rgb 0-1, intensiteetti 0-1) — rakenne harmaa/vaalea korkea
# intensiteetti (betoni/kipsi heijastaa); kaluste kirjava, matalampi intensiteetti.
_APPEAR = {
    0: ((0.72, 0.72, 0.70), 0.78),   # katto
    1: ((0.55, 0.55, 0.55), 0.70),   # lattia
    2: ((0.80, 0.78, 0.74), 0.80),   # seina
    7: ((0.45, 0.30, 0.20), 0.45),   # poyta (puu)
    9: ((0.60, 0.62, 0.65), 0.55),   # metalli/mep
    11: ((0.30, 0.45, 0.60), 0.40),  # kaappi/hylly (kirjava)
}


def _slab(rng, w, d, z, n, jitter=0.01):
    return np.column_stack([rng.uniform(0, w, n), rng.uniform(0, d, n),
                            np.full(n, z) + rng.normal(0, jitter, n)])


def _wall(rng, x0, y0, x1, y1, H, n, jitter=0.008):
    t = rng.uniform(0, 1, n); u = rng.uniform(0, 1, n)
    x = x0 + t * (x1 - x0) + rng.normal(0, jitter, n)
    y = y0 + t * (y1 - y0) + rng.normal(0, jitter, n)
    return np.column_stack([x, y, u * H])


def _box(rng, cx, cy, w, d, z0, z1, n, jitter=0.006):
    # 5 näkyvää pintaa (ei pohjaa)
    pts = []
    per = max(n // 5, 20)
    for (ax, bx, ay, by, az, bz) in [
        (cx-w/2, cx+w/2, cy-d/2, cy+d/2, z1, z1),          # top
        (cx-w/2, cx-w/2, cy-d/2, cy+d/2, z0, z1),          # sivut
        (cx+w/2, cx+w/2, cy-d/2, cy+d/2, z0, z1),
        (cx-w/2, cx+w/2, cy-d/2, cy-d/2, z0, z1),
        (cx-w/2, cx+w/2, cy+d/2, cy+d/2, z0, z1),
    ]:
        x = rng.uniform(min(ax, bx), max(ax, bx), per) if ax != bx else np.full(per, ax)
        y = rng.uniform(min(ay, by), max(ay, by), per) if ay != by else np.full(per, ay)
        z = rng.uniform(min(az, bz), max(az, bz), per) if az != bz else np.full(per, az)
        pts.append(np.column_stack([x + rng.normal(0, jitter, per),
                                    y + rng.normal(0, jitter, per), z]))
    return np.vstack(pts)


def _gen_synth_room(rng):
    W, D = rng.uniform(4, 8, 2); H = rng.uniform(2.7, 3.6)
    P, L = [], []
    def add(pts, lbl): P.append(pts); L.append(np.full(len(pts), lbl))
    dens = 900
    add(_slab(rng, W, D, 0.0, int(W*D*dens)), 1)
    add(_slab(rng, W, D, H, int(W*D*dens)), 0)
    for (x0, y0, x1, y1) in [(0,0,W,0),(0,D,W,D),(0,0,0,D),(W,0,W,D)]:
        add(_wall(rng, x0, y0, x1, y1, H, int(max(abs(x1-x0),abs(y1-y0))*H*dens)), 2)
    # kalusteet: matalia (poyta/tuoli) + TÄYSKORKEITA KAAPPEJA (avainkohde)
    nlow = rng.integers(2, 5)
    for _ in range(nlow):
        cx, cy = rng.uniform(0.6, W-0.6), rng.uniform(0.6, D-0.6)
        w, d = rng.uniform(0.4, 1.2, 2); h = rng.uniform(0.4, 1.0)
        add(_box(rng, cx, cy, w, d, 0, h, 2500), 7)
    ncab = rng.integers(1, 4)
    for _ in range(ncab):
        cx, cy = rng.uniform(0.5, W-0.5), rng.uniform(0.5, D-0.5)
        w, d = rng.uniform(0.35, 0.7, 2)
        add(_box(rng, cx, cy, w, d, 0, H-rng.uniform(0.0, 0.15), 4000), 11)  # täyskorkea kaappi
    pts = np.vstack(P).astype(np.float32); lbl = np.concatenate(L)
    # rikkaat piirteet per luokka
    rgb = np.zeros((len(pts), 3), np.float32); inten = np.zeros(len(pts), np.float32)
    for c in np.unique(lbl):
        m = lbl == c; base, ii = _APPEAR.get(int(c), ((0.5,0.5,0.5), 0.5))
        rgb[m] = np.clip(np.array(base) + rng.normal(0, 0.05, (m.sum(), 3)), 0, 1)
        inten[m] = np.clip(ii + rng.normal(0, 0.08, m.sum()), 0, 1)
    height = np.clip(pts[:, 2] / 3.0, 0, 1.5)
    extra = np.column_stack([rgb, inten, height]).astype(np.float32)
    return pts, lbl.astype(np.int64), extra


def _synth_blocks(n_rooms, max_bps, rng):
    F, L = [], []
    for _ in range(n_rooms):
        pts, lbl, extra = _gen_synth_room(rng)
        bf, bl = E._pts_to_blocks(pts, lbl, block_m=1.0, n_pts=4096, stride_m=0.5, extra=extra)
        if bf is None: continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        F.append(bf); L.append(bl)
    return (np.vstack(F), np.vstack(L)) if F else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True); ap.add_argument("--train", required=True)
    ap.add_argument("--val", required=True); ap.add_argument("--synth", type=int, default=40)
    ap.add_argument("--epochs", type=int, default=20); ap.add_argument("--voxel", type=float, default=0.03)
    ap.add_argument("--max-bps", type=int, default=300); ap.add_argument("--max-scenes", type=int, default=30)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"device={device}", flush=True)
    root = Path(a.root); rng = np.random.default_rng(7)
    tr = []; va = []
    for s in a.train.split(","): tr += sorted(glob.glob(str(root / f"site_{int(s):02d}" / "scene_*")))
    for s in a.val.split(","): va += sorted(glob.glob(str(root / f"site_{int(s):02d}" / "scene_*")))
    tr = tr[:a.max_scenes]; va = va[:12]
    t0 = time.time()
    rf, rl = FX._blocks(tr, a.voxel, True, a.max_bps, rng)     # Rohbau runko
    sf, sl = _synth_blocks(a.synth, a.max_bps, rng)            # synteettinen kaluste
    tf = np.vstack([rf, sf]); tl = np.vstack([rl, sl])
    vrf, vrl = FX._blocks(va, a.voxel, True, a.max_bps, rng)   # held-out Rohbau (rakenne)
    vsf, vsl = _synth_blocks(12, a.max_bps, rng)               # held-out synteettinen (kaluste)
    print(f"lohkot: Rohbau {len(rf)} + synth {len(sf)} = {len(tf)} train | "
          f"val Rohbau {len(vrf)}, val synth {len(vsf)} ({time.time()-t0:.0f}s)", flush=True)
    model = FX._train(tf, tl, 11, a.epochs, device, "COMBINED")
    sk_r, rr_r = FX._eval(model, vrf, vrl, device)
    sk_s, rr_s = FX._eval(model, vsf, vsl, device)
    print(f"==> HELD-OUT Rohbau (runko): rakenne-säilyy={sk_r:.3f}  krääsä-poisto={rr_r:.3f}", flush=True)
    print(f"==> HELD-OUT synth (kaluste): rakenne-säilyy={sk_s:.3f}  KALUSTE-poisto={rr_s:.3f}", flush=True)
    if a.out:
        import torch as T
        T.save({"model_state_dict": model.state_dict(), "in_ch": 11}, a.out)
        print(f"malli tallennettu: {a.out}", flush=True)


if __name__ == "__main__":
    main()

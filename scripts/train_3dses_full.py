"""Täysi 3DSES + Rohbau -koulutus. Bronze+Silver (66 skeneä, 12-luokkaa,
kaluste=Clutter) + Gold (7, 18-luokkaa) luetaan SUORAAN zipistä (ei purkua).
Rohbau = runko. Rikkaat piirteet rgb+korkeus (10). Held-out osa skeneistä + S171.

KORJAA edellisen bugin: per-tier-taksonomia (Bronze/Silver=12lk, Gold=18lk),
label AINA viimeisestä sarakkeesta.

Aja (.venv_train):
  python train_3dses_full.py --zip 3DSES.zip --rohbau DIR --rtrain 1,4,13 --epochs 20 --out M.pth
"""
import sys, glob, time, argparse, zipfile, io
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util
def _imp(n, p):
    s = importlib.util.spec_from_file_location(n, str(Path(__file__).parent / p)); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
E = _imp("exp", "export_s3dis_model.py"); FX = _imp("fx", "rohbau_feature_exp.py")
GEO = _imp("geo", "geo_feats.py"); COL = _imp("col", "column_feats_v2.py")
PAIR = _imp("pair", "pair_feats.py"); MSTORY = _imp("mstory", "multistory_gen.py")
VCLUT = _imp("vclut", "vclutter_gen.py")

# 12-luokka (Bronze/Silver) -> S3DIS 13. KEEP rakenne (0-6), REMOVE muut.
MAP12 = {0:3, 1:0, 2:6, 3:9, 4:9, 5:9, 6:2, 7:1, 8:1, 9:2, 10:5, 11:12}
# 18-luokka (Gold): 0 Column,1 Components,2 Covering,3 Damper,4 Door,5 Exit,
# 6 Fire,7 Furniture,8 Heater,9 Lamp,10 Outlet,11 Railing,12 Slab,13 Stair,
# 14 Switch,15 Wall,16 Window,17 Clutter
MAP18 = {0:3, 1:9, 2:0, 3:9, 4:6, 5:9, 6:9, 7:7, 8:9, 9:9, 10:9, 11:2, 12:1, 13:1, 14:9, 15:2, 16:5, 17:12}
_RM = [7, 8, 9, 10, 11, 12]


def _lut(mp):
    l = np.full(max(mp) + 1, 12, np.int64)
    for k, v in mp.items(): l[k] = v
    return l
LUT12, LUT18 = _lut(MAP12), _lut(MAP18)


def scene_blocks(z, name, mp_lut, voxel, max_bps, rng, geo=False, colf=False, pairf=False):
    with z.open(name) as f: a = np.load(io.BytesIO(f.read()))
    xyz = a[:, :3].astype(np.float32)
    rgb = (a[:, 3:6].astype(np.float32)) / 255.0
    raw = a[:, -1].astype(np.int64)                 # label AINA viimeinen sarake
    raw = np.clip(raw, 0, len(mp_lut) - 1)
    lbl = mp_lut[raw]
    idx = FX._voxel_repr_idx(xyz, voxel); xyz, rgb, lbl = xyz[idx], rgb[idx], lbl[idx]
    fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
    cols = [rgb, h[:, None]]
    if geo: cols.append(GEO.compute(xyz))
    if colf: cols.append(COL.compute(xyz))   # pystyjatkuvuus lasketaan SKENESTÄ, ei lohkosta
    if pairf: cols.append(PAIR.compute(xyz))  # seinäpari: vastapinta standardipaksuuden päässä
    extra = np.column_stack(cols).astype(np.float32)
    bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
    if bf is None: return None, None
    if len(bf) > max_bps:
        p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
    return bf, bl


def synth_retail_blocks(n_rooms, voxel, max_bps, rng, geo=False, colf=False, pairf=False, holdout_frac=0.15):
    """Synteettisiä liiketiloja (lattia-katto-hyllyrivit label 10 + tavaraa 12).

    3DSES ja Rohbau eivät sisällä myymälähyllyjä, joten niillä koulutettu malli
    ei osaa erottaa täyskorkeaa hyllyä seinästä — mitattu: samalla rakenne-
    tasolla 96 % hyllyistä jää, kun retail-koulutettu malli jättää 26 %.
    Väri = 0 (synteettisellä ei ole väriä; tuotantopolku on XYZ-only muutenkin).
    """
    tr_F, tr_L, va_F, va_L = [], [], [], []
    # holdout_frac=0 → kaikki koulutukseen: 3DSES-held-out pysyy silloin
    # vertailukelpoisena aiempiin ajoihin, ja hyllynpoisto mitataan erikseen
    # liiketilatestillä (joka ajaa myös tuotannon oikean inferenssipolun).
    nva = max(1, int(n_rooms * holdout_frac)) if holdout_frac > 0 else 0
    for i in range(n_rooms):
        xyz, lbl = E._gen_retail_room(rng)
        xyz = np.asarray(xyz, np.float32)
        idx = FX._voxel_repr_idx(xyz, voxel); xyz, lbl = xyz[idx], np.asarray(lbl).ravel()[idx]
        fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
        cols = [np.zeros((len(xyz), 3), np.float32), h[:, None]]
        if geo: cols.append(GEO.compute(xyz))
        if colf: cols.append(COL.compute(xyz))
        if pairf: cols.append(PAIR.compute(xyz))
        extra = np.column_stack(cols).astype(np.float32)
        bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
        if bf is None: continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        if i < nva: va_F.append(bf); va_L.append(bl)
        else: tr_F.append(bf); tr_L.append(bl)
        print(f"  liiketila {i+1}/{n_rooms}: {len(bf)} lohkoa", flush=True)
    if not tr_F: return None, None, None, None
    return (np.vstack(tr_F), np.vstack(tr_L),
            np.vstack(va_F) if va_F else None, np.vstack(va_L) if va_L else None)


def synth_multistory_blocks(n_rooms, voxel, max_bps, rng, geo=False, colf=False, pairf=False):
    """Monikorkeat skenet (palkit/pilarit/portaat välikorkeudella) koulutukseen.
    Kohdistaa mitatun heikon kohdan (rohbau site_10 palkki 71%). Kaikki
    koulutukseen (ei held-out) → 3DSES-held-out pysyy vertailukelpoisena."""
    F, Lb = [], []
    for i in range(n_rooms):
        xyz, lbl = MSTORY.gen(rng)
        idx = FX._voxel_repr_idx(xyz, voxel); xyz, lbl = xyz[idx], lbl[idx]
        fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
        cols = [np.zeros((len(xyz), 3), np.float32), h[:, None]]
        if geo: cols.append(GEO.compute(xyz))
        if colf: cols.append(COL.compute(xyz))
        if pairf: cols.append(PAIR.compute(xyz))
        extra = np.column_stack(cols).astype(np.float32)
        bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
        if bf is None: continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        F.append(bf); Lb.append(bl)
        print(f"  monikerros {i+1}/{n_rooms}: {len(bf)} lohkoa", flush=True)
    if not F: return None, None
    return np.vstack(F), np.vstack(Lb)


def synth_furnished_blocks(n_rooms, voxel, max_bps, rng, geo=False, colf=False, pairf=False):
    """Kalustetut huoneet (poydat/tuolit/kalusteet, label 7-12) koulutukseen.
    Korvaa 3DSES:n kalustepoisto-opetussignaalin, jotta painot ovat lisenssi-
    puhtaat mutta malli osaa yha poistaa asuntokalusteet (F2). Kaikki koulutukseen."""
    F, Lb = [], []
    for i in range(n_rooms):
        xyz, lbl = E._gen_room(rng)
        xyz = np.asarray(xyz, np.float32); lbl = np.asarray(lbl).ravel()
        idx = FX._voxel_repr_idx(xyz, voxel); xyz, lbl = xyz[idx], lbl[idx]
        fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
        cols = [np.zeros((len(xyz), 3), np.float32), h[:, None]]
        if geo: cols.append(GEO.compute(xyz))
        if colf: cols.append(COL.compute(xyz))
        if pairf: cols.append(PAIR.compute(xyz))
        extra = np.column_stack(cols).astype(np.float32)
        bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
        if bf is None: continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        F.append(bf); Lb.append(bl)
        print(f"  kalustettu {i+1}/{n_rooms}: {len(bf)} lohkoa", flush=True)
    if not F: return None, None
    return np.vstack(F), np.vstack(Lb)


def synth_vclutter_blocks(n_rooms, voxel, max_bps, rng, geo=False, colf=False, pairf=False):
    """Pysty-ohut-clutter-skenet (putket/tolpat/nurkkakasat label 12) koulutukseen.
    Kohdistaa 3dses_S171-valepilarit: suodatin luokitteli pystyputken window/door/
    wall:iksi. Opettaa isoloidun ohuen pystyn clutteriksi vaikka col_fill on korkea.
    Kaikki koulutukseen (ei held-out)."""
    F, Lb = [], []
    for i in range(n_rooms):
        xyz, lbl = VCLUT.gen(rng)
        idx = FX._voxel_repr_idx(xyz, voxel); xyz, lbl = xyz[idx], lbl[idx]
        fz = np.percentile(xyz[:, 2], 2); h = np.clip((xyz[:, 2] - fz) / 3.0, 0, 1.5)
        cols = [np.zeros((len(xyz), 3), np.float32), h[:, None]]
        if geo: cols.append(GEO.compute(xyz))
        if colf: cols.append(COL.compute(xyz))
        if pairf: cols.append(PAIR.compute(xyz))
        extra = np.column_stack(cols).astype(np.float32)
        bf, bl = E._pts_to_blocks(xyz, lbl, 1.0, 4096, 0.5, extra=extra)
        if bf is None: continue
        if len(bf) > max_bps:
            p = rng.choice(len(bf), max_bps, replace=False); bf, bl = bf[p], bl[p]
        F.append(bf); Lb.append(bl)
        print(f"  vclutter {i+1}/{n_rooms}: {len(bf)} lohkoa", flush=True)
    if not F: return None, None
    return np.vstack(F), np.vstack(Lb)


def dses_blocks(zip_path, tiers, voxel, max_bps, rng, holdout_frac=0.15, geo=False, colf=False, pairf=False):
    z = zipfile.ZipFile(zip_path)
    tr_F, tr_L, va_F, va_L = [], [], [], []
    for tier, lut in tiers:
        names = sorted([n for n in z.namelist() if n.startswith(tier + "/") and n.endswith(".npy")])
        nva = max(1, int(len(names) * holdout_frac))
        for i, n in enumerate(names):
            bf, bl = scene_blocks(z, n, lut, voxel, max_bps, rng, geo=geo, colf=colf, pairf=pairf)
            if bf is None: continue
            if i < nva: va_F.append(bf); va_L.append(bl)
            else: tr_F.append(bf); tr_L.append(bl)
        print(f"  {tier}: {len(names)} skeneä (held-out {nva})", flush=True)
    return (np.vstack(tr_F), np.vstack(tr_L), np.vstack(va_F), np.vstack(va_L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default="")   # 3DSES valinnainen: ilman sita painot ovat
                                           # CC BY-SA -vapaat (F2, lisenssipuhdas myyntiin)
    ap.add_argument("--rohbau", required=True)
    ap.add_argument("--rtrain", default="1,4,13"); ap.add_argument("--rval", default="7")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--voxel", type=float, default=0.03); ap.add_argument("--max-bps", type=int, default=200)
    ap.add_argument("--rmax", type=int, default=30); ap.add_argument("--out", default="")
    ap.add_argument("--arch", default="pointnet", choices=["pointnet", "dgcnn", "hybrid", "hybridpro"])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--cache", default="", help="npz-lohkovälimuisti — rakenna kerran, lataa jatkossa heti")
    ap.add_argument("--build-cache-only", action="store_true", help="rakenna vain välimuisti ja lopeta")
    ap.add_argument("--augment", action="store_true", help="data-augmentaatio (flip/kierto/jitter)")
    ap.add_argument("--geo", action="store_true", help="geometriset PCA-piirteet (verticality/planarity/sphericity)")
    ap.add_argument("--focal", action="store_true", help="focal loss (kohdistaa vaikeisiin rajatapauksiin)")
    ap.add_argument("--colfeat", action="store_true", help="pystyjatkuvuuspiirteet (col_fill/col_span/z_rel)")
    ap.add_argument("--pairfeat", action="store_true",
                    help="seinäparipiirteet (pair_score/pair_thickness)")
    ap.add_argument("--synth-retail", type=int, default=0,
                    help="synteettisiä liiketiloja koulutukseen (lattia-katto-hyllyt)")
    ap.add_argument("--synth-multistory", type=int, default=0,
                    help="synteettisiä monikorkeita skenejä (palkit/pilarit/portaat välikorkeudella)")
    ap.add_argument("--synth-vclutter", type=int, default=0,
                    help="synteettisiä pysty-ohut-clutter-skenejä (putket/tolpat/nurkkakasat → clutter)")
    ap.add_argument("--synth-furnished", type=int, default=0,
                    help="synteettisiä kalustettuja huoneita (pöydät/tuolit/kalusteet → poista; korvaa 3DSES:n F2)")
    a = ap.parse_args()
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"; print(f"device={device}", flush=True)
    rng = np.random.default_rng(13); t0 = time.time()
    if a.cache and Path(a.cache).exists():
        z = np.load(a.cache)
        tf, tl, dvf, dvl = z["tf"], z["tl"], z["dvf"], z["dvl"]
        print(f"lohkot VÄLIMUISTISTA {a.cache}: train {len(tf)}, held-out {len(dvf)} ({time.time()-t0:.0f}s)", flush=True)
    else:
        # Rohbau (rakenne) on aina ankkuri; 3DSES (--zip) on valinnainen lisä.
        r_tr = []
        for s in a.rtrain.split(","): r_tr += sorted(glob.glob(str(Path(a.rohbau) / f"site_{int(s):02d}" / "scene_*")))
        r_tr = r_tr[:a.rmax]
        rf, rl = FX._blocks(r_tr, a.voxel, True, a.max_bps, rng, geo=a.geo, colf=a.colfeat, pairf=a.pairfeat)
        rf = np.delete(rf, 9, axis=2)   # poista intensiteetti → base6+rgb3+h1[+geo3][+col3]
        if a.zip:
            tiers = [("Bronze", LUT12), ("Silver", LUT12), ("Gold", LUT18)]
            dtf, dtl, dvf, dvl = dses_blocks(a.zip, tiers, a.voxel, a.max_bps, rng, geo=a.geo, colf=a.colfeat, pairf=a.pairfeat)
            parts_f, parts_l = [dtf, rf], [dtl, rl]
            n_dses = len(dtf)
        else:
            # Ilman 3DSES:aa held-out tulee Rohbau-held-out-sitesta (EI koulutuksessa).
            rv = []
            for s in a.rval.split(","): rv += sorted(glob.glob(str(Path(a.rohbau) / f"site_{int(s):02d}" / "scene_*")))[:2]
            dvf, dvl = FX._blocks(rv, a.voxel, True, a.max_bps, rng, geo=a.geo, colf=a.colfeat, pairf=a.pairfeat)
            dvf = np.delete(dvf, 9, axis=2)
            parts_f, parts_l = [rf], [rl]
            n_dses = 0
        n_ret, n_ms = 0, 0
        if a.synth_retail:
            sf, sl, svf, svl = synth_retail_blocks(a.synth_retail, a.voxel, a.max_bps, rng,
                                                   geo=a.geo, colf=a.colfeat, pairf=a.pairfeat, holdout_frac=0.0)
            if sf is not None:
                parts_f.append(sf); parts_l.append(sl); n_ret = len(sf)
                # liiketila-held-out mukaan: 3DSES ei mittaa hyllynpoistoa lainkaan
                if svf is not None:
                    dvf = np.vstack([dvf, svf]); dvl = np.vstack([dvl, svl])
        if a.synth_multistory:
            mf, ml = synth_multistory_blocks(a.synth_multistory, a.voxel, a.max_bps, rng,
                                             geo=a.geo, colf=a.colfeat, pairf=a.pairfeat)
            if mf is not None:
                parts_f.append(mf); parts_l.append(ml); n_ms = len(mf)
        n_vc = 0
        if a.synth_vclutter:
            vf, vl = synth_vclutter_blocks(a.synth_vclutter, a.voxel, a.max_bps, rng,
                                           geo=a.geo, colf=a.colfeat, pairf=a.pairfeat)
            if vf is not None:
                parts_f.append(vf); parts_l.append(vl); n_vc = len(vf)
        n_fu = 0
        if a.synth_furnished:
            ff, fl = synth_furnished_blocks(a.synth_furnished, a.voxel, a.max_bps, rng,
                                            geo=a.geo, colf=a.colfeat, pairf=a.pairfeat)
            if ff is not None:
                parts_f.append(ff); parts_l.append(fl); n_fu = len(ff)
        tf = np.vstack(parts_f); tl = np.vstack(parts_l)
        print(f"lohkot: 3DSES {n_dses} + Rohbau {len(rf)} + liiketila {n_ret} + monikerros {n_ms} "
              f"+ vclutter {n_vc} + kalustettu {n_fu} = {len(tf)} train | held-out {len(dvf)} ({time.time()-t0:.0f}s)", flush=True)
        if a.cache:
            np.savez(a.cache, tf=tf, tl=tl, dvf=dvf, dvl=dvl)
            print(f"välimuisti tallennettu: {a.cache}", flush=True)
    if a.build_cache_only:
        print("vain välimuisti pyydetty — lopetetaan.", flush=True); return
    in_ch = tf.shape[2]                           # koko kanavamäärä (base6 + extrat)
    model = FX._train(tf, tl, in_ch, a.epochs, device, f"3DSES-{a.arch}", arch=a.arch,
                      batch=a.batch, augment=a.augment, focal=a.focal)
    sk, rr = FX._eval(model, dvf, dvl, device)
    print(f"==> HELD-OUT 3DSES: rakenne-säilyy={sk:.3f}  kaluste/krääsä-poisto={rr:.3f}", flush=True)
    if a.out:
        import torch as T; T.save({"model_state_dict": model.state_dict(), "in_ch": in_ch}, a.out)
        print(f"malli tallennettu: {a.out} (in_ch={in_ch})", flush=True)


if __name__ == "__main__":
    main()

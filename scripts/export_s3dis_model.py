"""Vie S3DIS PointNet -malli ONNX-muotoon → models/s3dis_pointnet.onnx.

Vaatii erikseen: pip install torch --index-url https://download.pytorch.org/whl/cpu

Vaihtoehto A — valmiit painot (suositeltu):
  1. Avaa: https://github.com/yanx27/Pointnet_Pointnet2_pytorch
  2. README → Pretrained models → S3DIS (Area-5) → pointnet_sem_seg → best_model.pth
  3. python scripts/export_s3dis_model.py --weights best_model.pth

Vaihtoehto B — harjoita synteettisellä datalla (ei ulkoisia tiedostoja tarvita):
  python scripts/export_s3dis_model.py --synth
  Generoi 500 virtuaalihuonetta (lattia/katto/seinät/huonekalut), harjoittaa
  ~30 min CPU:lla. Ei yhtä hyvä kuin A mutta toimii heti.

Vaihtoehto C — harjoita 3DSES-datalla jos löytyy oikeat labeltiedostot:
  python scripts/export_s3dis_model.py --train --data data/_3dses

Tulos: models/s3dis_pointnet.onnx
build.ps1 bundlaa sen automaattisesti exe:hen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Arkkitehtuuri — täsmälleen yanx27/Pointnet_Pointnet2_pytorch pointnet_sem_seg
# Samat parametrinimet → best_model.pth latautuu suoraan.
# ---------------------------------------------------------------------------

def _build_model(k: int = 13, in_ch: int = 9):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class _Encoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv1d(in_ch, 64, 1)
            self.conv2 = nn.Conv1d(64, 128, 1)
            self.conv3 = nn.Conv1d(128, 1024, 1)
            self.bn1 = nn.BatchNorm1d(64)
            self.bn2 = nn.BatchNorm1d(128)
            self.bn3 = nn.BatchNorm1d(1024)

        def forward(self, x):           # (B, 9, N) → (B, 1088, N)
            B, _, N = x.size()
            x = F.relu(self.bn1(self.conv1(x)))
            pointfeat = x
            x = F.relu(self.bn2(self.conv2(x)))
            x = self.bn3(self.conv3(x))
            x = torch.max(x, 2, keepdim=True)[0]
            x = x.view(-1, 1024, 1).expand(-1, -1, N)
            return torch.cat([x, pointfeat], 1)

    class _Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.feat = _Encoder()
            self.conv1 = nn.Conv1d(1088, 512, 1)
            self.conv2 = nn.Conv1d(512, 256, 1)
            self.conv3 = nn.Conv1d(256, 128, 1)
            self.conv4 = nn.Conv1d(128, k, 1)
            self.bn1 = nn.BatchNorm1d(512)
            self.bn2 = nn.BatchNorm1d(256)
            self.bn3 = nn.BatchNorm1d(128)
            self.dropout = nn.Dropout(p=0.3)

        def forward(self, x):           # (B, N, 9) → (B, N, k)
            x = x.permute(0, 2, 1)
            x = self.feat(x)
            x = F.relu(self.bn1(self.conv1(x)))
            x = self.dropout(F.relu(self.bn2(self.conv2(x))))
            x = F.relu(self.bn3(self.conv3(x)))
            x = self.conv4(x)
            return x.permute(0, 2, 1)

    return _Model()


# ---------------------------------------------------------------------------
# Vaihtoehto A — lataa valmiit painot
# ---------------------------------------------------------------------------

def load_pretrained(model, path: Path) -> None:
    import torch
    ckpt = torch.load(str(path), map_location="cpu", weights_only=True)
    state = ckpt.get("model_state_dict") or ckpt.get("state_dict") or ckpt
    missing, _ = model.load_state_dict(state, strict=False)
    real_missing = [k for k in missing if "fstn" not in k]
    if real_missing:
        print(f"VAROITUS: puuttuvat avaimet: {real_missing[:5]}")
    else:
        print(f"Painot ladattu: {path}  ({path.stat().st_size//1024} KB)")


# ---------------------------------------------------------------------------
# Vaihtoehto B — synteettinen harjoitusdata
# ---------------------------------------------------------------------------

# S3DIS-taksonomia: 0 katto, 1 lattia, 2 seinä, 3 pilari, 4 palkki, 5 ikkuna,
# 6 ovi (= rakenne, SÄILYTETÄÄN); 7–12 kalusteet/krääsä (POISTETAAN).
# Talotekniikka (putket/kanavat/kaapelihyllyt/valaisimet) EI ole arkkitehtonista
# rakennetta → label 12 (krääsä) → suodatin poistaa sen ja palkkidetektori ei
# näe kattoon ripustettua LVIS-tavaraa palkkeina. Tämä on juuri se ero joka
# tuottaa "miljardi turhaa palkkia" sotkuisissa liiketila/työmaaskanneissa.
_LBL_CLUTTER = 12


def _undulate(rng, xy, amp: float):
    """Matalataajuinen sileä poikkeama (m) xy-tasolla — oikea pinta ei ole taso.
    Palauttaa 0.0 jos amp<=0 (skalaari summautuu vektoriin)."""
    import numpy as np
    if amp <= 0:
        return 0.0
    fx, fy = rng.uniform(0.15, 0.6, 2)
    px, py = rng.uniform(0.0, 6.283, 2)
    return amp * np.sin(fx * xy[:, 0] + px) * np.cos(fy * xy[:, 1] + py)


def _gen_stray(rng, W: float, D: float, H: float, density: float):
    """Hajapisteet VAIN katon ylä- ja lattian alapuolelle (skannerikohinan aito
    sijainti: heijastukset ikkunoista, keilaimen artefaktit tilan ulkopuolella).
    Vaihtelee skenen z-aluetta kuten oikeassa skannissa (jossa z-normalisointi ei
    ala tarkalleen lattiasta) → malli ei ylikiinnity oletukseen 'lattia=0,katto=1'.

    HUOM: EI sisätilaan (0..H) — aiempi versio ripotteli krääsää koko tilavuuteen
    ja opetti mallin poistamaan sisätilan pisteet → oikean karkean skannin
    rakennepinnat katosivat. Label 12 (krääsä, poistetaan)."""
    import numpy as np
    n = rng.integers(0, max(1, int(density * W * D * 0.04)))   # harva
    if n <= 0:
        return (np.empty((0, 3), dtype=np.float32), np.empty(0, dtype=np.int64))
    x = rng.uniform(0, W, n); y = rng.uniform(0, D, n)
    below = rng.uniform(-0.25, -0.02, n)
    above = rng.uniform(H + 0.02, H + 0.35, n)
    z = np.where(rng.random(n) < 0.5, below, above)            # vain tilan ulkopuolelle
    pts = np.c_[x, y, z].astype(np.float32)
    return pts, np.full(n, _LBL_CLUTTER, dtype=np.int64)


def _gen_mep(rng, W: float, D: float, H: float, density: float):
    """Generoi kattoon ripustetun talotekniikan (putket, kanavat, kaapelihyllyt).

    Kaikki VAAKASUORIA, pitkänomaisia ja kattovyöhykkeessä (z lähellä kattoa) —
    juuri ne piirteet joiden takia ne menevät palkkidetektorissa palkeiksi.
    Label 12 (krääsä) → malli oppii poistamaan. Palauttaa (pts Nx3, lbl N)."""
    import numpy as np

    pts_list, lbl_list = [], []

    def _emit(arr):
        if len(arr):
            pts_list.append(arr)
            lbl_list.append(np.full(len(arr), _LBL_CLUTTER, dtype=np.int64))

    def _axis_run(rng):
        """Palauttaa (suunta-akseli 0/1, kiinteä poikittaiskoord, alku, loppu)."""
        if rng.random() < 0.5:                       # X-suuntainen veto
            fixed = rng.uniform(0.15 * D, 0.85 * D)
            return 0, fixed, rng.uniform(0.05 * W, 0.25 * W), rng.uniform(0.75 * W, 0.95 * W)
        fixed = rng.uniform(0.15 * W, 0.85 * W)      # Y-suuntainen veto
        return 1, fixed, rng.uniform(0.05 * D, 0.25 * D), rng.uniform(0.75 * D, 0.95 * D)

    def _line_points(axis, fixed, lo, hi, z, n):
        """Pisteet vaakasuoran janan varrelle (poikittais- ja z-hajonta annetaan kutsujalle)."""
        t = rng.uniform(lo, hi, n)
        base = np.empty((n, 3), dtype=np.float32)
        if axis == 0:
            base[:, 0] = t; base[:, 1] = fixed; base[:, 2] = z
        else:
            base[:, 0] = fixed; base[:, 1] = t; base[:, 2] = z
        return base

    # --- Putkiniput: 1–3 rinnakkaista pyöreää putkea (LV/lämmitys/sprinkleri) ---
    n_pipe_bundles = rng.integers(0, 3)
    for _ in range(n_pipe_bundles):
        axis, fixed, lo, hi = _axis_run(rng)
        length = abs(hi - lo)
        if length < 1.0:
            continue
        z0 = rng.uniform(H - 0.55, H - 0.12)         # roikkuu katon alla
        n_in_bundle = rng.integers(1, 4)
        for pj in range(n_in_bundle):
            radius = rng.uniform(0.02, 0.13)         # 40–260 mm putki
            off = pj * rng.uniform(0.08, 0.22)       # rinnakkaisten väli
            n_pipe = max(120, int(density * length * 2 * np.pi * radius))
            # pyöreä pinta: kulma + akselisijainti
            ang = rng.uniform(0, 2 * np.pi, n_pipe)
            base = _line_points(axis, fixed + off, lo, hi, z0, n_pipe)
            # poikittais- ja pystysiirto putken säteellä (pyöreä poikkileikkaus)
            cross = radius * np.cos(ang)
            vert = radius * np.sin(ang)
            if axis == 0:
                base[:, 1] += cross
            else:
                base[:, 0] += cross
            base[:, 2] += vert
            base += rng.normal(0, 0.003, base.shape).astype(np.float32)
            _emit(base)

    # --- Ilmastointikanava: iso suorakaide-poikkileikkaus (4 pitkää pintaa) ---
    if rng.random() < 0.6:
        axis, fixed, lo, hi = _axis_run(rng)
        length = abs(hi - lo)
        if length >= 1.5:
            cw = rng.uniform(0.30, 0.75)             # kanavan leveys
            ch = rng.uniform(0.25, 0.55)             # kanavan korkeus
            z_top = rng.uniform(H - 0.35, H - 0.10)
            z_bot = z_top - ch
            n_face = max(150, int(density * length * ch))
            for side in (-cw / 2, cw / 2):           # kaksi pystysivua
                base = _line_points(axis, fixed, lo, hi, 0.0, n_face)
                zc = rng.uniform(z_bot, z_top, n_face)
                base[:, 2] = zc
                if axis == 0:
                    base[:, 1] += side
                else:
                    base[:, 0] += side
                base += rng.normal(0, 0.004, base.shape).astype(np.float32)
                _emit(base)
            n_bt = max(120, int(density * length * cw))
            for zc in (z_bot, z_top):                # ala- ja yläpinta
                base = _line_points(axis, fixed, lo, hi, zc, n_bt)
                cross = rng.uniform(-cw / 2, cw / 2, n_bt)
                if axis == 0:
                    base[:, 1] += cross
                else:
                    base[:, 0] += cross
                base += rng.normal(0, 0.004, base.shape).astype(np.float32)
                _emit(base)

    # --- Kaapelihylly: matala leveä vaakakaista katon alla ---
    if rng.random() < 0.5:
        axis, fixed, lo, hi = _axis_run(rng)
        length = abs(hi - lo)
        if length >= 1.0:
            tw = rng.uniform(0.10, 0.40)
            z0 = rng.uniform(H - 0.45, H - 0.15)
            n_tray = max(120, int(density * length * tw * 1.5))
            base = _line_points(axis, fixed, lo, hi, z0, n_tray)
            cross = rng.uniform(-tw / 2, tw / 2, n_tray)
            if axis == 0:
                base[:, 1] += cross
            else:
                base[:, 0] += cross
            base[:, 2] += rng.uniform(-0.02, 0.02, n_tray)
            base += rng.normal(0, 0.004, base.shape).astype(np.float32)
            _emit(base)

    if not pts_list:
        return (np.empty((0, 3), dtype=np.float32), np.empty(0, dtype=np.int64))
    return (np.vstack(pts_list).astype(np.float32), np.concatenate(lbl_list))


def _gen_retail_room(rng, n_pts: int = 120_000):
    """Synteettinen LIIKETILA: iso halli + lattia-katto-hyllyrivit (label 10)
    + tavaraa hyllyillä (label 12). Hyllyrivit läpäisevät geometrisen pysty-
    maskin ja näyttävät seiniltä — suodattimen on opittava ne pois."""
    import numpy as np

    W = rng.uniform(10.0, 25.0)
    D = rng.uniform(8.0, 20.0)
    H = rng.uniform(3.0, 5.0)
    surf = float(rng.uniform(0.005, 0.028))          # per-halli pintakarkeus
    density = n_pts / (2 * (W * D + W * H + D * H) + 0.001)

    pts_list, lbl_list = [], []

    def _emit(n, label):
        pts_list.append(n); lbl_list.append(np.full(len(n), label, dtype=np.int64))

    n_floor = max(200, int(density * W * D))
    xy = rng.uniform([0, 0], [W, D], (n_floor, 2))
    _emit(np.c_[xy, rng.normal(0.0, surf, n_floor) + _undulate(rng, xy, rng.uniform(0, 0.03))], 1)
    _emit(np.c_[xy + rng.uniform(-0.01, 0.01, (n_floor, 2)),
                rng.normal(H, surf, n_floor) + _undulate(rng, xy, rng.uniform(0, 0.03))], 0)

    for axis, fixed, lo, hi in [(0, 0.0, 0, D), (0, W, 0, D), (1, 0.0, 0, W), (1, D, 0, W)]:
        n_wall = max(100, int(density * (hi - lo) * H))
        u = rng.uniform(lo, hi, n_wall)
        v = rng.uniform(0.0, H, n_wall)
        tilt = rng.uniform(-0.03, 0.03)
        noise = rng.normal(0, surf, n_wall) + tilt * (v - H / 2)
        w = (np.c_[np.full(n_wall, fixed) + noise, u, v] if axis == 0
             else np.c_[u, np.full(n_wall, fixed) + noise, v])
        _emit(w, 2)

    # Hyllyrivit: yhdensuuntaiset, käytävävälein, LÄHES kattoon (myymälähylly
    # 2.0–2.5m tai varastohylly kattoon asti)
    n_rows = rng.integers(2, 6)
    aisle = rng.uniform(1.2, 2.5)
    shelf_d = rng.uniform(0.4, 1.0)
    y0 = rng.uniform(1.0, 2.5)
    for r in range(n_rows):
        ry = y0 + r * (shelf_d + aisle)
        if ry + shelf_d > D - 1.0:
            break
        sh_h = rng.uniform(2.0, H - rng.uniform(0.0, 0.4))
        x0 = rng.uniform(0.5, 2.0)
        x1 = W - rng.uniform(0.5, 2.0)
        seg_len = x1 - x0
        if seg_len < 2.0:
            continue
        # hyllyn päädyt + molemmat pitkät pystypinnat (kuin ohut "seinä")
        n_face = max(150, int(density * seg_len * sh_h))
        for fy in (ry, ry + shelf_d):
            u = rng.uniform(x0, x1, n_face)
            v = rng.uniform(0.0, sh_h, n_face)
            _emit(np.c_[u, np.full(n_face, fy) + rng.normal(0, 0.01, n_face), v], 10)
        # hyllytasot + tavaraa (epätasainen täyttö)
        n_lvl = rng.integers(3, 7)
        for lv in range(n_lvl):
            lz = (lv + 1) * sh_h / (n_lvl + 1)
            n_g = max(60, int(density * seg_len * shelf_d * 0.8))
            gx = rng.uniform(x0, x1, n_g)
            gy = rng.uniform(ry, ry + shelf_d, n_g)
            gz = lz + rng.uniform(0.0, 0.35, n_g)
            keep = rng.random(n_g) < rng.uniform(0.4, 0.9)
            if keep.any():
                _emit(np.c_[gx[keep], gy[keep], gz[keep]], 12)

    # Kattoon ripustettu talotekniikka (putket/kanavat/kaapelihyllyt) — LVIS-
    # täyteisiä liiketiloja/varastoja varten. Näkyy palkkidetektorille
    # valepalkkeina ellei suodatin poista sitä.
    mep_pts, mep_lbl = _gen_mep(rng, W, D, H, density)
    if len(mep_pts):
        pts_list.append(mep_pts); lbl_list.append(mep_lbl)

    # Hajapisteet (skannerikohina) → z-alueen vaihtelu kuten oikeassa skannissa
    stray_pts, stray_lbl = _gen_stray(rng, W, D, H, density)
    if len(stray_pts):
        pts_list.append(stray_pts); lbl_list.append(stray_lbl)

    pts = np.vstack(pts_list).astype(np.float32)
    lbl = np.concatenate(lbl_list).astype(np.int64)
    return pts, lbl


def _gen_room(rng, n_pts: int = 80_000):
    """Generoi yksi synteettinen huone, palauttaa (pts Nx3, labels N) metreinä."""
    import numpy as np

    W = rng.uniform(3.0, 9.0)
    D = rng.uniform(3.0, 9.0)
    H = rng.uniform(2.4, 3.5)
    # DOMAIN RANDOMIZATION: per-huone pintakarkeus 5–28 mm (oikea betoni/muotti-
    # pinta on karkea; malli EI saa oppia että vain siisti taso = rakenne).
    surf = float(rng.uniform(0.005, 0.028))
    density = n_pts / (2 * (W * D + W * H + D * H) + 0.001)

    pts_list, lbl_list = [], []

    def _plane(n, label):
        pts_list.append(n); lbl_list.append(np.full(len(n), label, dtype=np.int64))

    # Lattia (label 1) + katto (label 0) — lievä aaltoilu (ei täysin taso)
    n_floor = max(100, int(density * W * D))
    xy = rng.uniform([0, 0], [W, D], (n_floor, 2))
    z_floor = rng.normal(0.0, surf, n_floor) + _undulate(rng, xy, amp=rng.uniform(0, 0.02))
    z_ceil  = rng.normal(H,   surf, n_floor) + _undulate(rng, xy, amp=rng.uniform(0, 0.02))
    floor_pts = np.c_[xy, z_floor]
    ceil_pts  = np.c_[xy + rng.uniform(-0.01, 0.01, (n_floor, 2)), z_ceil]
    _plane(floor_pts, 1); _plane(ceil_pts, 0)

    # Seinät (label 2) — 4 seinää, lievä kallistus (muottiseinä ei täysin suora)
    for axis, fixed, lo, hi in [
        (0, 0.0, 0, D), (0, W,   0, D),
        (1, 0.0, 0, W), (1, D,   0, W),
    ]:
        n_wall = max(50, int(density * (hi - lo) * H))
        u = rng.uniform(lo, hi, n_wall)
        v = rng.uniform(0.0, H,  n_wall)
        tilt = rng.uniform(-0.03, 0.03)                  # ~±1.7° kallistus korkeuden yli
        noise = rng.normal(0, surf, n_wall) + tilt * (v - H / 2)
        if axis == 0:
            w = np.c_[np.full(n_wall, fixed) + noise, u, v]
        else:
            w = np.c_[u, np.full(n_wall, fixed) + noise, v]
        _plane(w, 2)

    # Huonekalut — pöydät (label 7) ja tuolit (label 8)
    n_furniture = rng.integers(1, 8)
    for _ in range(n_furniture):
        kind = rng.integers(0, 3)      # 0=pöytä, 1=tuoli, 2=kaappi
        if kind == 0:                   # pöytä
            fw, fd = rng.uniform(0.6, 1.6), rng.uniform(0.6, 1.0)
            fh_bot, fh_top = sorted((rng.uniform(0.68, 0.75), rng.uniform(0.68, 0.75)))
            label = 7
        elif kind == 1:                 # tuoli
            fw, fd = rng.uniform(0.4, 0.6), rng.uniform(0.4, 0.6)
            fh_bot, fh_top = rng.uniform(0.42, 0.48), rng.uniform(0.80, 0.95)
            label = 8
        else:                           # kaappi/hylly
            fw, fd = rng.uniform(0.3, 0.6), rng.uniform(0.8, 1.8)
            fh_bot, fh_top = rng.uniform(0.0, 0.1), rng.uniform(0.9, 2.0)
            label = 10

        fx = rng.uniform(0.3, max(0.31, W - fw - 0.3))
        fy = rng.uniform(0.3, max(0.31, D - fd - 0.3))

        n_obj = max(30, int(density * 2 * (fw * fd + fw * (fh_top - fh_bot) + fd * (fh_top - fh_bot))))
        ox = rng.uniform(fx, fx + fw, n_obj)
        oy = rng.uniform(fy, fy + fd, n_obj)
        oz = rng.uniform(fh_bot, fh_top, n_obj)
        obj_pts = np.c_[ox, oy, oz] + rng.normal(0, 0.003, (n_obj, 3))
        _plane(obj_pts, label)

    # Talotekniikka myös asunnoissa/toimistoissa (osassa) — käytävien ja
    # aputilojen kattopinnat, jotta malli oppii LVIS:n pois kaikkialla.
    if rng.random() < 0.5:
        mep_pts, mep_lbl = _gen_mep(rng, W, D, H, density)
        if len(mep_pts):
            pts_list.append(mep_pts); lbl_list.append(mep_lbl)

    # Hajapisteet (skannerikohina) → vaihtelee z-aluetta kuten oikea skanni
    stray_pts, stray_lbl = _gen_stray(rng, W, D, H, density)
    if len(stray_pts):
        pts_list.append(stray_pts); lbl_list.append(stray_lbl)

    pts = np.vstack(pts_list).astype(np.float32)
    lbl = np.concatenate(lbl_list).astype(np.int64)
    return pts, lbl


def _pts_to_blocks(pts, lbl, block_m: float = 1.0, n_pts: int = 4096, stride_m: float = 0.5,
                   extra=None):
    """Jakaa huoneen 1m×1m lohkoihin, palauttaa (feats (B,N,6+E), labels (B,N)).

    extra: valinnainen per-piste (N, E) lisäpiirretaulukko (esim. [r,g,b,intensity,
    height]) joka kirjoitetaan piirreslotteihin 6.. — taaksepäin-yhteensopiva:
    extra=None → E=3 nolla-rgb-slottia → sama 9-piirrevektori kuin ennen.

    Ämpäröinti: pisteet lajitellaan kertaalleen stride-soluihin, ja koska
    block_m == 2*stride_m, lohkon rajat osuvat tarkalleen solurajoihin →
    lohko (i,j) kattaa täsmälleen solut {i,i+1}×{j,j+1}. Tarkka maski
    säilytetään mutta ajetaan vain pienelle ehdokasjoukolle → O(N log N)
    lohkojen O(ruudut × N) sijaan (retail-huoneet 176k pistettä × ~500 ruutua)."""
    import numpy as np

    sc_min = pts.min(0); sc_range = np.maximum(pts.max(0) - sc_min, 1e-6)
    x_steps = np.arange(sc_min[0], pts[:, 0].max() - block_m + 1e-6, stride_m)
    y_steps = np.arange(sc_min[1], pts[:, 1].max() - block_m + 1e-6, stride_m)
    if len(x_steps) == 0 or len(y_steps) == 0:
        return None, None

    # Ryhmittele pistteet stride-soluihin (solun leveys = stride_m).
    cellx = np.floor((pts[:, 0] - sc_min[0]) / stride_m).astype(np.int64)
    celly = np.floor((pts[:, 1] - sc_min[1]) / stride_m).astype(np.int64)
    ncy = int(celly.max()) + 2
    ckey = cellx * ncy + celly
    order = np.argsort(ckey, kind="stable")
    ckey_sorted = ckey[order]
    uniq, starts = np.unique(ckey_sorted, return_index=True)
    ends = np.append(starts[1:], len(order))
    cell_map = {int(u): order[s:e] for u, s, e in zip(uniq, starts, ends)}

    blocks_f, blocks_l = [], []
    for bi, cx in enumerate(x_steps):
        for bj, cy in enumerate(y_steps):
            # ehdokkaat lohkon 2×2 stride-soluista
            cand = [cell_map[k] for k in (
                bi * ncy + bj, bi * ncy + bj + 1,
                (bi + 1) * ncy + bj, (bi + 1) * ncy + bj + 1,
            ) if k in cell_map]
            if not cand:
                continue
            cidx = np.concatenate(cand)
            # tarkka lohkomaski pienelle ehdokasjoukolle (identtinen jäsenyys)
            sub = pts[cidx]
            m = (
                (sub[:, 0] >= cx) & (sub[:, 0] < cx + block_m) &
                (sub[:, 1] >= cy) & (sub[:, 1] < cy + block_m)
            )
            idx = cidx[m]
            if len(idx) < 32:
                continue
            if len(idx) >= n_pts:
                sel = np.random.choice(len(idx), n_pts, replace=False)
            else:
                sel = np.concatenate([np.arange(len(idx)),
                                       np.random.choice(len(idx), n_pts - len(idx))])
            picked = idx[sel]
            s = pts[picked]
            n_extra = 3 if extra is None else extra.shape[1]
            f = np.zeros((n_pts, 6 + n_extra), dtype=np.float32)
            f[:, 0] = (s[:, 0] - cx) / block_m
            f[:, 1] = (s[:, 1] - cy) / block_m
            f[:, 2] = (s[:, 2] - sc_min[2]) / sc_range[2]
            f[:, 3] = (s[:, 0] - sc_min[0]) / sc_range[0]
            f[:, 4] = (s[:, 1] - sc_min[1]) / sc_range[1]
            f[:, 5] = (s[:, 2] - sc_min[2]) / sc_range[2]
            if extra is not None:
                f[:, 6:6 + n_extra] = extra[picked]
            blocks_f.append(f)
            blocks_l.append(lbl[picked])

    if not blocks_f:
        return None, None
    return np.stack(blocks_f), np.stack(blocks_l)


def train_synthetic(model, n_rooms: int = 500, epochs: int = 80,
                    batch: int = 8, n_pts: int = 4096, retail_frac: float = 0.0,
                    max_blocks_per_room: int = 0) -> None:
    """Harjoita PUHTAASTI synteettisellä datalla — ei ulkoisia datasettejä.

    retail_frac: osuus huoneista jotka generoidaan liiketiloina (lattia-katto-
    hyllyrivit label 10 → suodatin oppii poistamaan ne). 0.0 = vain asunnot/
    toimistot (oletusmalli), ~0.5 = liiketilamalli (osaa yhä tavalliset seinät).
    max_blocks_per_room: >0 → poimi satunnaisesti korkeintaan näin monta lohkoa
    per huone (CPU-budjetti: variaatio tulee monesta huoneesta, ei yhdestä isosta
    retail-huoneesta joka tuottaa ~690 lohkoa)."""
    import os
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.optim as optim

    torch.set_num_threads(os.cpu_count() or 8)   # CPU-koulutus: käytä kaikki ytimet
    print(f"torch-säikeet: {torch.get_num_threads()}", flush=True)
    rng = np.random.default_rng(42)
    kind = "liiketila-painotettu" if retail_frac > 0 else "asunto/toimisto"
    print(f"Generoidaan {n_rooms} synteettistä huonetta ({kind}, retail_frac={retail_frac})...", flush=True)

    all_feats, all_lbls = [], []
    for i in range(n_rooms):
        if retail_frac > 0 and rng.random() < retail_frac:
            pts, lbl = _gen_retail_room(rng)
        else:
            pts, lbl = _gen_room(rng)
        f, l = _pts_to_blocks(pts, lbl, n_pts=n_pts)
        if f is not None:
            if max_blocks_per_room > 0 and len(f) > max_blocks_per_room:
                pick = rng.choice(len(f), max_blocks_per_room, replace=False)
                f, l = f[pick], l[pick]
            all_feats.append(f); all_lbls.append(l)
        if (i + 1) % 25 == 0:
            nb = sum(len(x) for x in all_feats)
            print(f"  {i+1}/{n_rooms} huonetta, {nb} lohkoa", flush=True)

    all_feats = np.vstack(all_feats)   # (total_blocks, N, 9)
    all_lbls  = np.vstack(all_lbls)    # (total_blocks, N)
    print(f"Lohkoja yhteensä: {len(all_feats)}")

    # Luokkapainot — kompensoi epätasapaino
    flat_lbls = all_lbls.ravel()
    counts = np.bincount(flat_lbls, minlength=13).astype(np.float32)
    counts = np.maximum(counts, 1)
    weights = torch.tensor(1.0 / counts, dtype=torch.float32)
    weights = weights / weights.sum() * 13          # normalisoi

    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=30, gamma=0.5)
    criterion = nn.CrossEntropyLoss(weight=weights)
    model.train()

    n_blocks = len(all_feats)
    steps_per_epoch = max(20, n_blocks // batch)

    for epoch in range(epochs):
        losses = []
        idx_all = np.random.permutation(n_blocks)
        for step in range(steps_per_epoch):
            bi = idx_all[step * batch % n_blocks: step * batch % n_blocks + batch]
            if len(bi) == 0:
                bi = idx_all[:batch]
            x = torch.tensor(all_feats[bi])   # (B, N, 9)
            y = torch.tensor(all_lbls[bi])     # (B, N)
            optimizer.zero_grad()
            logits = model(x)                  # (B, N, 13)
            loss = criterion(logits.reshape(-1, 13), y.reshape(-1))
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        scheduler.step()

        if (epoch + 1) % 3 == 0 or epoch == 0:
            avg = sum(losses) / len(losses)
            # Nopea tarkkuus satunnaisotoksella (ei vain ensimmäiset lohkot)
            with torch.no_grad():
                si = np.random.permutation(n_blocks)[:64]
                sample_x = torch.tensor(all_feats[si])
                sample_y = all_lbls[si].ravel()
                pred = model(sample_x).reshape(-1, 13).argmax(1).numpy()
                keep_cls = [7, 8, 9, 10, 11, 12]
                is_furn_gt   = np.isin(sample_y, keep_cls)
                is_furn_pred = np.isin(pred,      keep_cls)
                # rakenne säilyy = rakennepiste ei mene kalusteeksi (recall structural)
                struct_keep = (~is_furn_pred[~is_furn_gt]).mean() if (~is_furn_gt).any() else 1.0
                furn_rm = (is_furn_pred[is_furn_gt]).mean() if is_furn_gt.any() else 0.0
            print(f"Epoch {epoch+1:3d}/{epochs}  loss={avg:.4f}  "
                  f"rakenne-säilyy={struct_keep:.3f}  kaluste-poisto={furn_rm:.3f}", flush=True)

    print("Harjoitus valmis.")


# ---------------------------------------------------------------------------
# Vaihtoehto C — harjoita 3DSES-datalla (jos on oikeat labeltiedostot)
# ---------------------------------------------------------------------------

def _voxel_downsample(pts, lbl, voxel_m: float = 0.03):
    """Harvenna voxel-gridillä, säilytä yleisin label per voxel."""
    import numpy as np
    keys = np.floor(pts / voxel_m).astype(np.int64)
    key1d = keys[:, 0] * 10_000_000 + keys[:, 1] * 1_000 + keys[:, 2]
    order = np.argsort(key1d, kind="stable")
    key_s, pts_s, lbl_s = key1d[order], pts[order], lbl[order]
    _, first = np.unique(key_s, return_index=True)
    return pts_s[first], lbl_s[first]


def train_on_3dses(model, data_dir: Path, epochs: int = 50) -> None:
    import glob, numpy as np, torch, torch.nn as nn, torch.optim as optim
    import time

    files = sorted(glob.glob(str(data_dir / "*.npy")))
    if not files:
        print(f"Ei .npy-tiedostoja: {data_dir}")
        sys.exit(1)

    N_BLOCK = 4096
    print("Poimitaan lohkot etukäteen (kerran)...", flush=True)

    # Poimi lohkot per-tiedosto KERRAN → (B, 4096, 9) ja (B, 4096)
    all_feats, all_lbls = [], []
    for f in files:
        t0 = time.time()
        a = np.load(f)
        if a.ndim != 2 or a.shape[1] < 7:
            continue
        pts = a[:, :3].astype(np.float32)
        lbl = a[:, 6].astype(np.int64)
        # Harvenna 30 mm voxeliin → masking nopeutuu rajusti
        pts, lbl = _voxel_downsample(pts, lbl, 0.03)
        bf, bl = _pts_to_blocks(pts, lbl, block_m=1.0, n_pts=N_BLOCK, stride_m=0.5)
        if bf is not None:
            all_feats.append(bf); all_lbls.append(bl)
        print(f"  {Path(f).name}: {len(pts):,} pistetta (harvennettu) "
              f"-> {0 if bf is None else len(bf)} lohkoa  ({time.time()-t0:.0f}s)", flush=True)

    all_feats = np.vstack(all_feats)   # (total_blocks, 4096, 9)
    all_lbls  = np.vstack(all_lbls)    # (total_blocks, 4096)
    n_blocks  = len(all_feats)
    print(f"Lohkoja yhteensä: {n_blocks}", flush=True)

    # Luokkapainot epätasapainolle (kalusteita vähän → painota)
    counts = np.bincount(all_lbls.ravel(), minlength=13).astype(np.float32)
    counts = np.maximum(counts, 1)
    weights = torch.tensor((1.0 / counts) / (1.0 / counts).sum() * 13, dtype=torch.float32)

    BATCH = 8
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=20, gamma=0.5)
    criterion = nn.CrossEntropyLoss(weight=weights)
    model.train()

    for epoch in range(epochs):
        losses = []
        perm = np.random.permutation(n_blocks)
        for i in range(0, n_blocks, BATCH):
            bi = perm[i:i + BATCH]
            x = torch.tensor(all_feats[bi])
            y = torch.tensor(all_lbls[bi])
            optimizer.zero_grad()
            loss = criterion(model(x).reshape(-1, 13), y.reshape(-1))
            loss.backward(); optimizer.step(); losses.append(loss.item())
        scheduler.step()
        if losses:
            print(f"Epoch {epoch+1}/{epochs}  loss={sum(losses)/len(losses):.4f}", flush=True)


# ---------------------------------------------------------------------------
# Vaihtoehto D — harjoita Rohbau3D:llä (CC-BY-4.0, OIKEAT per-piste-labelit)
# ---------------------------------------------------------------------------

# Rohbau3D 17 luokkaa → 13-luokkainen S3DIS-taksonomia jonka suodatin osaa.
# Rakenne → 0–6 (SÄILYTETÄÄN), talotekniikka + tausta → 12 (krääsä, POISTETAAN).
# Suodatin välittää vain keep/remove-jaosta (0–6 vs 7–12), joten rakenteen
# tarkka aliluokka ei ole kriittinen — TGA (17) ja None (0) menevät krääsäksi.
_ROHBAU_TO_S3DIS = {
    0: 12,   # None/tausta → krääsä (poista)
    1: 0,    # Ceiling → katto
    2: 0,    # Slanted Ceiling → katto
    3: 0,    # Ceiling Cutout → katto
    4: 1,    # Floor → lattia
    5: 2,    # Wall → seinä
    6: 2,    # Drywall → seinä
    7: 2,    # Wall Cutout → seinä
    8: 2,    # Parapet → seinä
    9: 3,    # Beam → palkki
    10: 4,   # Column → pilari
    11: 4,   # Staircase → (rakenne, säilytä)
    12: 5,   # Window Cutout → ikkuna
    13: 5,   # Window → ikkuna
    14: 6,   # Door Rough Opening → ovi
    15: 2,   # Facade Element → seinä (rakenne)
    16: 6,   # Elevator Doors → ovi (rakenne)
    17: 9,   # TGA (talotekniikka/MEP) → OMA poistoluokka 9 (erillään Nonesta 12,
             # jotta malli oppii putki/kanava-geometrian eikä sekoita sitä
             # hajanaiseen taustaan; molemmat luokat 7-12 poistetaan silti).
}


def _map_rohbau_labels(cls):
    import numpy as np
    lut = np.full(int(cls.max()) + 1, 12, dtype=np.int64)
    for k, v in _ROHBAU_TO_S3DIS.items():
        if k < len(lut):
            lut[k] = v
    return lut[cls]


def train_on_rohbau(model, data_dir: Path, val_scenes: list[str],
                    epochs: int = 12, voxel_m: float = 0.03,
                    max_blocks_per_scene: int = 400) -> None:
    """Harjoita Rohbau3D:n OIKEILLA per-piste-labeleilla (CC-BY-4.0).

    Oikea keilausdata → ei sim-to-real-kuilua kuten synteettisellä. val_scenes
    jätetään pois (rehellinen held-out-validointi). Koordinaatit METREINÄ (kuten
    _pts_to_blocks olettaa)."""
    import os, glob, time
    import numpy as np
    import torch
    import torch.nn as nn
    import torch.optim as optim

    torch.set_num_threads(os.cpu_count() or 8)
    print(f"torch-säikeet: {torch.get_num_threads()}", flush=True)

    scene_dirs = sorted(glob.glob(str(data_dir / "scene_*")))
    train_dirs = [d for d in scene_dirs if not any(v in os.path.basename(d) for v in val_scenes)]
    print(f"Rohbau3D: {len(train_dirs)} koulutus-skeneä, held-out {val_scenes}", flush=True)

    rng = np.random.default_rng(42)
    all_feats, all_lbls = [], []
    for d in train_dirs:
        t0 = time.time()
        xyz = np.load(os.path.join(d, "coord.npy")).astype(np.float32)   # metrit
        cls = np.load(os.path.join(d, "class.npy")).astype(np.int64)
        lbl = _map_rohbau_labels(cls)
        pts, lbl = _voxel_downsample(xyz, lbl, voxel_m)
        bf, bl = _pts_to_blocks(pts, lbl, block_m=1.0, n_pts=4096, stride_m=0.5)
        if bf is not None:
            if len(bf) > max_blocks_per_scene:
                pick = rng.choice(len(bf), max_blocks_per_scene, replace=False)
                bf, bl = bf[pick], bl[pick]
            all_feats.append(bf); all_lbls.append(bl)
        print(f"  {os.path.basename(d)}: {len(pts):,} pistetta -> "
              f"{0 if bf is None else len(bf)} lohkoa ({time.time()-t0:.0f}s)", flush=True)

    all_feats = np.vstack(all_feats)
    all_lbls = np.vstack(all_lbls)
    n_blocks = len(all_feats)
    print(f"Lohkoja yhteensä: {n_blocks}", flush=True)

    counts = np.bincount(all_lbls.ravel(), minlength=13).astype(np.float32)
    counts = np.maximum(counts, 1)
    weights = torch.tensor((1.0 / counts) / (1.0 / counts).sum() * 13, dtype=torch.float32)

    BATCH = 8
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=6, gamma=0.5)
    criterion = nn.CrossEntropyLoss(weight=weights)
    model.train()

    for epoch in range(epochs):
        losses = []
        perm = np.random.permutation(n_blocks)
        for i in range(0, n_blocks, BATCH):
            bi = perm[i:i + BATCH]
            x = torch.tensor(all_feats[bi]); y = torch.tensor(all_lbls[bi])
            optimizer.zero_grad()
            loss = criterion(model(x).reshape(-1, 13), y.reshape(-1))
            loss.backward(); optimizer.step(); losses.append(loss.item())
        scheduler.step()
        if (epoch + 1) % 2 == 0 or epoch == 0:
            with torch.no_grad():
                si = np.random.permutation(n_blocks)[:64]
                pred = model(torch.tensor(all_feats[si])).reshape(-1, 13).argmax(1).numpy()
                sy = all_lbls[si].ravel()
                rm = [7, 8, 9, 10, 11, 12]
                gt_rm = np.isin(sy, rm); pr_rm = np.isin(pred, rm)
                sk = (~pr_rm[~gt_rm]).mean() if (~gt_rm).any() else 1.0
                rr = pr_rm[gt_rm].mean() if gt_rm.any() else 0.0
            print(f"Epoch {epoch+1:3d}/{epochs}  loss={sum(losses)/len(losses):.4f}  "
                  f"rakenne-säilyy={sk:.3f}  krääsä-poisto={rr:.3f}", flush=True)
    print("Harjoitus valmis.")


# ---------------------------------------------------------------------------
# ONNX-vienti
# ---------------------------------------------------------------------------

def export_onnx(model, out_path: Path, n_pts: int = 4096) -> None:
    import torch
    model.eval()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Tallenna painot ENSIN — jos ONNX-vienti kaatuu, harjoitus ei mene hukkaan.
    ckpt_path = out_path.with_suffix(".pth")
    torch.save(model.state_dict(), str(ckpt_path))
    print(f"Painot tallennettu: {ckpt_path}", flush=True)

    dummy = torch.zeros(1, n_pts, 9)
    torch.onnx.export(
        model, dummy, str(out_path),
        input_names=["input"], output_names=["output"],
        dynamic_axes={"input": {1: "N"}, "output": {1: "N"}},
        opset_version=17,
        dynamo=False,          # käytä vakaata legacy-vientiä (ei vaadi onnxscriptia)
    )
    print(f"Viety: {out_path}  ({out_path.stat().st_size//1024} KB)")
    print("Kopioi models/-hakemistoon ja aja build.ps1.")


# ---------------------------------------------------------------------------

def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_default = repo_root / "models" / "s3dis_pointnet.onnx"

    ap = argparse.ArgumentParser(description="Vie S3DIS PointNet ONNX-muotoon")
    ap.add_argument("--weights", type=Path, default=None,
                    help="Pretrained .pth (Pointnet_Pointnet2_pytorch pointnet_sem_seg)")
    ap.add_argument("--synth", action="store_true",
                    help="Harjoita synteettisellä datalla (ei ulkoisia tiedostoja)")
    ap.add_argument("--synth-rooms", type=int, default=500,
                    help="Synteettisten huoneiden määrä (oletus 500)")
    ap.add_argument("--synth-epochs", type=int, default=80,
                    help="Harjoitusepokit (oletus 80)")
    ap.add_argument("--synth-retail", type=float, default=0.0,
                    help="Osuus liiketilahuoneita (0.0=oletusmalli, 0.5=liiketilamalli)")
    ap.add_argument("--synth-max-blocks", type=int, default=0,
                    help="Max lohkoa per huone (CPU-budjetti; 0=ei rajaa)")
    ap.add_argument("--train", action="store_true",
                    help="Harjoita 3DSES-datalla (--data pakollinen)")
    ap.add_argument("--rohbau", type=Path, default=None,
                    help="Harjoita Rohbau3D:llä (CC-BY, oikeat labelit); polku extracted/site_XX")
    ap.add_argument("--rohbau-val", nargs="+", default=["02004", "02007", "02010"],
                    help="Held-out validointiskenet (ei mukaan koulutukseen)")
    ap.add_argument("--data", type=Path, default=repo_root / "data" / "_3dses")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--out", type=Path, default=out_default)
    args = ap.parse_args()

    try:
        import torch  # noqa: F401
    except ImportError:
        print("PyTorch puuttuu.")
        print("Asenna: pip install torch --index-url https://download.pytorch.org/whl/cpu")
        sys.exit(1)

    model = _build_model(k=13)

    if args.weights:
        if not args.weights.exists():
            print(f"Tiedostoa ei löydy: {args.weights}"); sys.exit(1)
        load_pretrained(model, args.weights)
    elif args.synth:
        train_synthetic(model, n_rooms=args.synth_rooms, epochs=args.synth_epochs,
                        retail_frac=args.synth_retail,
                        max_blocks_per_room=args.synth_max_blocks)
    elif args.rohbau:
        train_on_rohbau(model, args.rohbau, val_scenes=args.rohbau_val, epochs=args.epochs)
    elif args.train:
        train_on_3dses(model, args.data, epochs=args.epochs)
    else:
        print("Käytä: --weights <pth> | --synth | --rohbau <dir> | --train --data <dir>")
        sys.exit(1)

    export_onnx(model, args.out)


if __name__ == "__main__":
    main()

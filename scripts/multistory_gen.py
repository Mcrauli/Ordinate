"""Synteettiset monikorkeat koulutusskenet, S3DIS-labelein.

Kohdistaa mitatun heikon kohdan: rohbau site_10/scene_10000 palkki 71%,
portaat 83% (v2). 3DSES/Rohbau-koulutuksessa on vain vähän välikorkeuden
palkkeja ja portaita → verkko epävarma. Nämä opettavat ne suoraan.

S3DIS: 0 katto, 1 lattia, 2 seina, 3 palkki, 4 pilari, 6 ovi, 12 krassa.
Koordinaatit METREINA (kuten _pts_to_blocks olettaa). Väri = 0 (XYZ-only).
"""
import numpy as np


def _px(x, y0, y1, z0, z1, n, rng, s=0.01):
    return np.column_stack([np.full(n, x) + rng.normal(0, s, n),
                            rng.uniform(y0, y1, n), rng.uniform(z0, z1, n)])


def _py(y, x0, x1, z0, z1, n, rng, s=0.01):
    return np.column_stack([rng.uniform(x0, x1, n), np.full(n, y) + rng.normal(0, s, n),
                            rng.uniform(z0, z1, n)])


def _pz(x0, x1, y0, y1, z, n, rng, s=0.01):
    return np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n),
                            z + rng.normal(0, s, n)])


def gen(rng):
    """Yksi satunnainen monikorkea skene. Palauttaa (xyz metreina, lbl)."""
    P, L = [], []

    def add(p, c):
        P.append(p); L.append(np.full(len(p), c, np.int64))

    kind = rng.integers(0, 3)
    W = rng.uniform(6, 14); D = rng.uniform(6, 12)
    surf = float(rng.uniform(0.006, 0.025))

    if kind == 0:      # korkea halli, korkea palkki + pilarit
        H = rng.uniform(5.5, 9.0)
        add(_pz(0, W, 0, D, 0, 6000, rng, surf), 1)
        add(_pz(0, W, 0, D, H, 6000, rng, surf), 0)
        for x in (0.0, W): add(_px(x, 0, D, 0, H, 5000, rng, surf), 2)
        for y in (0.0, D): add(_py(y, 0, W, 0, H, 5000, rng, surf), 2)
        beam_z = rng.uniform(H * 0.55, H * 0.8)          # VALIKORKEUS
        add(_pz(1, W - 1, D / 2 - 0.15, D / 2 + 0.15, beam_z, 2500, rng, surf), 3)
        for cx in rng.uniform(2, W - 2, rng.integers(2, 4)):   # pilarit lattiasta kattoon
            add(np.column_stack([cx + rng.normal(0, surf, 2000),
                                 rng.uniform(2, D - 2, 2000).clip(D / 2 - 0.15, D / 2 + 0.15) * 0 +
                                 rng.uniform(D / 2 - 0.15, D / 2 + 0.15, 2000),
                                 rng.uniform(0, H, 2000)]), 4)
        add(rng.uniform([1, 1, 0], [W - 1, D - 1, 1.4], size=(3500, 3)), 12)

    elif kind == 1:    # kaksikerroksinen: valilattia + palkki valikorkeudella + portaat
        add(_pz(0, W, 0, D, 0, 6000, rng, surf), 1)
        add(_pz(0, W, 0, D, 3.0, 6000, rng, surf), 1)     # valilattia
        add(_pz(0, W, 0, D, 6.0, 6000, rng, surf), 0)
        for x in (0.0, W): add(_px(x, 0, D, 0, 6, 7000, rng, surf), 2)
        for y in (0.0, D): add(_py(y, 0, W, 0, 6, 7000, rng, surf), 2)
        add(_pz(1, W - 1, 1.0, 1.3, 2.8, 2500, rng, surf), 3)   # palkki 2.8 m
        t = rng.uniform(0, 1, 4000)                             # portaat L1->L2 (label lattia)
        add(np.column_stack([1 + t * 3, np.full(4000, D - 1) + rng.normal(0, 0.05, 4000),
                             t * 3 + rng.normal(0, 0.03, 4000)]), 1)
        add(rng.uniform([2, 2, 0], [W - 2, D - 2, 0.9], size=(2500, 3)), 12)
        add(rng.uniform([2, 2, 3], [W - 2, D - 2, 3.9], size=(2500, 3)), 12)

    else:              # erikorkuiset vierekkaiset huoneet
        Ha, Hb = rng.uniform(2.5, 3.0), rng.uniform(4.0, 5.5)
        add(_pz(0, W / 2, 0, D, 0, 5000, rng, surf), 1); add(_pz(0, W / 2, 0, D, Ha, 5000, rng, surf), 0)
        add(_pz(W / 2, W, 0, D, 0, 5000, rng, surf), 1); add(_pz(W / 2, W, 0, D, Hb, 5000, rng, surf), 0)
        for x in (0.0, W / 2, W):
            hh = Ha if x <= W / 2 else Hb
            add(_px(x, 0, D, 0, hh, 5000, rng, surf), 2)
        for y in (0.0, D): add(_py(y, 0, W, 0, max(Ha, Hb), 6000, rng, surf), 2)
        add(rng.uniform([0.5, 0.5, 0], [W / 2 - 0.5, D - 0.5, 1.2], size=(2500, 3)), 12)
        add(rng.uniform([W / 2 + 0.5, 0.5, 0], [W - 0.5, D - 0.5, 1.8], size=(2500, 3)), 12)

    return np.vstack(P).astype(np.float32), np.concatenate(L)

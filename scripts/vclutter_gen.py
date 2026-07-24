"""Synteettiset PYSTY-OHUT-CLUTTER-skenet, S3DIS-labelein.

Kohdistaa mitatun heikon kohdan (3dses_S171): kalustesuodatin luokittelee
pystyputken / nurkkakaman window/door/wall:iksi (rakenne → säilyy) → geometrinen
pilaridetektori tekee siitä VALEPILARIN. Juurisyy: koulutuksessa ei ole
isoloituja ohuita pystyelementtejä clutterina; ikkuna/ovi ovat pystysuoria
ohuita alueita → verkko yleistää putken ikkunaksi.

Nämä skenet opettavat suoraan: ISOLOITU OHUT PYSTY (putki/tolppa/kanava/
nurkkakasa) = clutter (12, POISTA), vaikka se ulottuisi lattiasta kattoon
(korkea col_fill). Kontrastiksi seinissä on OIKEITA ikkunoita/ovia (5/6) jotta
verkko oppii eron: planaari-osa-seinää = ikkuna; isoloitu ohut = putki.

S3DIS: 0 katto, 1 lattia, 2 seina, 5 ikkuna, 6 ovi, 12 krassa.
Koordinaatit METREINA (kuten _pts_to_blocks olettaa). Vari = 0 (XYZ-only).
"""
import numpy as np


def _pipe(cx, cy, z0, z1, r, n, rng, s=0.006):
    """Pystyputken pinta (lieriö)."""
    th = rng.uniform(0, 2 * np.pi, n)
    z = rng.uniform(z0, z1, n)
    rr = r + rng.normal(0, s, n)
    return np.column_stack([cx + rr * np.cos(th), cy + rr * np.sin(th), z])


def _post(cx, cy, z0, z1, w, d, n, rng, s=0.006):
    """Nelikulmaisen tolpan/kanavan 4 pystypintaa."""
    parts = []
    per = max(1, n // 4)
    for (ax, sgn) in [("x", -1), ("x", 1), ("y", -1), ("y", 1)]:
        z = rng.uniform(z0, z1, per)
        if ax == "x":
            x = np.full(per, cx + sgn * w / 2) + rng.normal(0, s, per)
            y = rng.uniform(cy - d / 2, cy + d / 2, per)
        else:
            x = rng.uniform(cx - w / 2, cx + w / 2, per)
            y = np.full(per, cy + sgn * d / 2) + rng.normal(0, s, per)
        parts.append(np.column_stack([x, y, z]))
    return np.vstack(parts)


def _blob_column(cx, cy, z0, z1, w, d, n, rng):
    """Tayteinen epasaannollinen pystykasa (nurkkakama/tavarapino)."""
    return np.column_stack([
        rng.uniform(cx - w / 2, cx + w / 2, n),
        rng.uniform(cy - d / 2, cy + d / 2, n),
        rng.uniform(z0, z1, n),
    ])


def gen(rng):
    """Yksi satunnainen pysty-clutter-skene. Palauttaa (xyz metreina, lbl)."""
    P, L = [], []

    def add(p, c):
        if len(p):
            P.append(p); L.append(np.full(len(p), c, np.int64))

    W = rng.uniform(5, 12); D = rng.uniform(5, 10); H = rng.uniform(2.5, 4.2)
    surf = float(rng.uniform(0.006, 0.02))

    def _pz(x0, x1, y0, y1, z, n):
        return np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n),
                                z + rng.normal(0, surf, n)])

    def _wall(axis, v, z0, z1, n, holes=()):
        # seinapinta; holes = lista (a0,a1,hz0,hz1) joissa EI seinapistetta (aukko)
        if axis == "x":
            a = rng.uniform(0, D, n); z = rng.uniform(z0, z1, n)
            keep = np.ones(n, bool)
            for (a0, a1, hz0, hz1) in holes:
                keep &= ~((a > a0) & (a < a1) & (z > hz0) & (z < hz1))
            return np.column_stack([np.full(n, v) + rng.normal(0, surf, n), a, z])[keep]
        else:
            a = rng.uniform(0, W, n); z = rng.uniform(z0, z1, n)
            keep = np.ones(n, bool)
            for (a0, a1, hz0, hz1) in holes:
                keep &= ~((a > a0) & (a < a1) & (z > hz0) & (z < hz1))
            return np.column_stack([a, np.full(n, v) + rng.normal(0, surf, n), z])[keep]

    # lattia + katto
    add(_pz(0, W, 0, D, 0, 7000), 1)
    add(_pz(0, W, 0, D, H, 7000), 0)

    # seinat, joissa OIKEITA ikkunoita/ovia (kontrasti putkiin)
    win = (rng.uniform(1, D - 2), None)
    wy0 = rng.uniform(0.9, 1.2)
    holes_x0 = [(win[0], win[0] + rng.uniform(1.0, 1.8), wy0, wy0 + rng.uniform(1.0, 1.5))]
    add(_wall("x", 0.0, 0, H, 7000, holes=holes_x0), 2)
    # ikkuna-pinta (label 5) aukon kohdalle (ohut, MUTTA planaari osa seinaa)
    (a0, a1, hz0, hz1) = holes_x0[0]
    add(np.column_stack([np.full(1500, 0.0) + rng.normal(0, surf, 1500),
                         rng.uniform(a0, a1, 1500), rng.uniform(hz0, hz1, 1500)]), 5)
    # ovi toisessa seinassa
    dx = rng.uniform(1, W - 2)
    holes_y0 = [(dx, dx + rng.uniform(0.9, 1.1), 0.0, rng.uniform(2.0, 2.2))]
    add(_wall("y", 0.0, 0, H, 7000, holes=holes_y0), 2)
    (da0, da1, dz0, dz1) = holes_y0[0]
    add(np.column_stack([rng.uniform(da0, da1, 1500),
                         np.full(1500, 0.0) + rng.normal(0, surf, 1500),
                         rng.uniform(dz0, dz1, 1500)]), 6)
    add(_wall("x", W, 0, H, 7000), 2)
    add(_wall("y", D, 0, H, 7000), 2)

    # ISOLOIDUT PYSTY-CLUTTER-elementit (label 12) — vaihtelevat tyypit/sijainnit
    n_cl = int(rng.integers(3, 8))
    for _ in range(n_cl):
        # osa lahelle seinaa (kuten S171 ~0.35 m), osa vapaana
        near_wall = rng.random() < 0.5
        if near_wall:
            side = rng.integers(0, 4)
            off = rng.uniform(0.25, 0.6)
            if side == 0:   cx, cy = off, rng.uniform(0.5, D - 0.5)
            elif side == 1: cx, cy = W - off, rng.uniform(0.5, D - 0.5)
            elif side == 2: cx, cy = rng.uniform(0.5, W - 0.5), off
            else:           cx, cy = rng.uniform(0.5, W - 0.5), D - off
        else:
            cx, cy = rng.uniform(1.2, W - 1.2), rng.uniform(1.2, D - 1.2)
        # useimmat lattiasta kattoon (korkea col_fill = vaikea tapaus)
        full = rng.random() < 0.7
        z0 = 0.0 if full else rng.uniform(0, 0.4)
        z1 = H if full else rng.uniform(H * 0.5, H)
        kind = rng.integers(0, 3)
        if kind == 0:       # pyorea putki
            r = rng.uniform(0.025, 0.13)
            add(_pipe(cx, cy, z0, z1, r, int(rng.integers(1500, 3000)), rng, surf), 12)
        elif kind == 1:     # nelikulmainen tolppa/kanava
            w = rng.uniform(0.08, 0.26); d = rng.uniform(0.08, 0.26)
            add(_post(cx, cy, z0, z1, w, d, int(rng.integers(1800, 3200)), rng, surf), 12)
        else:               # epasaannollinen pystykasa (nurkkatavara)
            w = rng.uniform(0.12, 0.4); d = rng.uniform(0.12, 0.4)
            add(_blob_column(cx, cy, z0, z1, w, d, int(rng.integers(2000, 3500)), rng), 12)

    # matalaa tavaraa realismiksi
    add(rng.uniform([1, 1, 0], [W - 1, D - 1, 1.0], size=(2500, 3)), 12)

    return np.vstack(P).astype(np.float32), np.concatenate(L)

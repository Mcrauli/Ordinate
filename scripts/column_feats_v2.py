"""Monikorkeus-robustit pystyjatkuvuuspiirteet.

column_feats.py normalisoi z_rel/col_span KOKO SKENEN korkeudella. 6.2 m tilassa
palkki 2.8 m korkeudella sai z_rel 0.45 = koulutuksen kalustevyohyke -> verkko
luuli palkkia poydaksi (mitattu: rohbau site_10/scene_10000, palkki 100%->49%,
pilari 97%->59%, portaat 100%->63%).

Korjaus: kaikki kolme lasketaan PAIKALLISEN sarakelattian ja KIINTEAN
kerroskorkeuden (3 m) suhteen. Palkki 2.8 m oman lattiansa ylapuolella lukee
0.93 (kattovyohyke, rakenne) rakennuksen kokonaiskorkeudesta riippumatta.

Palauttaa (N,3): [col_fill, col_span, z_story]
  col_fill  = tayttyneet z-binit / sarakkeen OMA lattia-katto-vali (0-1)
  col_span  = sarakkeen korkeus / 3 m kerrosreferenssi, clip (0-1)
  z_story   = pisteen korkeus OMAN sarakelattian ylapuolella / 3 m, clip (0-1)
"""
import numpy as np

CELL_M = 0.10
Z_BIN_M = 0.20
STORY_M = 3.0          # kerrosreferenssi: seina/palkki lukee ~1 tassa mittakaavassa


def compute(xyz: np.ndarray, cell_m: float = CELL_M, z_bin_m: float = Z_BIN_M) -> np.ndarray:
    xyz = np.ascontiguousarray(xyz[:, :3].astype(np.float64))
    n = len(xyz)
    if n < 8:
        return np.zeros((n, 3), np.float32)
    lo = xyz.min(axis=0)
    z = xyz[:, 2]

    gx = np.floor((xyz[:, 0] - lo[0]) / cell_m).astype(np.int64)
    gy = np.floor((xyz[:, 1] - lo[1]) / cell_m).astype(np.int64)
    gz = np.clip(np.floor((z - lo[2]) / z_bin_m).astype(np.int64), 0, None)
    nz = int(gz.max()) + 1

    ny = int(gy.max()) + 1
    ucol, cinv = np.unique(gx * ny + gy, return_inverse=True)

    # sarakekohtainen paikallinen lattia ja katto (EI globaali)
    col_floor = np.full(len(ucol), np.inf)
    col_ceil = np.full(len(ucol), -np.inf)
    np.minimum.at(col_floor, cinv, z)
    np.maximum.at(col_ceil, cinv, z)
    local_h = np.maximum(col_ceil - col_floor, 1e-6)

    # tayttyneet z-binit per sarake
    upair = np.unique(cinv.astype(np.int64) * nz + gz)
    filled = np.bincount(upair // nz, minlength=len(ucol)).astype(np.float64)

    # col_fill jaetaan KIINTEALLA kerrosbinimaaralla (ei paikallisella): littea
    # lattia (1 bini) lukee ~0, seina (kerroksellinen) ~1, riippumatta rakennuksen
    # kokonaiskorkeudesta. Paikallinen jako tekisi lattiasta "taynnä" (1/1).
    story_bins = STORY_M / z_bin_m
    col_fill = np.clip(filled / story_bins, 0.0, 1.0)[cinv]
    col_span = np.clip(local_h / STORY_M, 0.0, 1.0)[cinv]
    z_story = np.clip((z - col_floor[cinv]) / STORY_M, 0.0, 1.0)

    return np.column_stack([col_fill, col_span, z_story]).astype(np.float32)

"""Seinaparipiirre: onko pisteen pinnalla VASTAKKAINEN yhdensuuntainen pinta
standardipaksuuden etaisyydella?

Aidolla seinalla on kaksi pintaa 66-300 mm etaisyydella (sama tosiasia jolla
_thickness_lock_walls mittaa paksuuden). Myymalahyllyn syvyys on 400-1000 mm
-> se putoaa alueen ULKOPUOLELLE. Tama on se erotin jota sarakepiirteessa ei
ole: taysikorkea hylly tayttaa XY-sarakkeen kuten seina, mutta sen syvyys ei
ole seinan paksuus. Tavoite on ratkaista liiketila ILMAN hyllydataa.

Mitattu synteettisella (CELL_M 0.06): seina 200 mm 89.1 %, hylly 600 mm 0.2 %,
lattia 1.5 %. Karkeampi ruutu 0.08 nostaa seinan 98.6 %:iin mutta hyvaksyy
puolet hyllyista ja koko lattian -> ruutukokoa EI saa kasvattaa seinaluvun
perusteella.

Yksikot: METREINA, kuten geo_feats.py ja column_feats.py (koulutusdata on
metreissa). Tuotantoportti kayttaa millimetreja.

Palauttaa (N,2): [pair_score, pair_thickness] — 0 jos vastapintaa ei ole.
"""
import numpy as np
from scipy.spatial import cKDTree

CELL_M = 0.06
D_MIN, D_MAX, D_STEP = 0.06, 0.32, 0.02
_MIN_SCORE = 0.7          # normaalien yhdensuuntaisuus jotta pari kelpaa


def _sign(n):
    """Vakaa merkkisaanto: suurin komponentti positiiviseksi. HUOM: sign(n_z)
    EI kelpaa — pystyseinan normaali on vaakasuora, jolloin n_z ~ 0 ja merkki
    heiluu kohinan mukaan (mitattu: seinan paritunnistus jai 59 %:iin)."""
    i = np.abs(n).argmax(axis=1)
    return np.sign(n[np.arange(len(n)), i] + 1e-12)[:, None]


def compute(xyz: np.ndarray, k: int = 16) -> np.ndarray:
    xyz = np.ascontiguousarray(xyz[:, :3].astype(np.float64))
    n = len(xyz)
    if n < k + 1:
        return np.zeros((n, 2), np.float32)

    _, idx = cKDTree(xyz).query(xyz, k=k, workers=-1)
    nb = xyz[idx]
    nb = nb - nb.mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / k
    nrm = np.linalg.eigh(cov)[1][:, :, 0]           # pienin ominaisarvo = normaali
    nrm_u = nrm * _sign(nrm)

    lo = xyz.min(axis=0)
    cell = np.floor((xyz - lo) / CELL_M).astype(np.int64)
    ny, nz = cell[:, 1].max() + 2, cell[:, 2].max() + 2
    key = (cell[:, 0] * ny + cell[:, 1]) * nz + cell[:, 2]
    ukey, inv = np.unique(key, return_inverse=True)

    cn = np.zeros((len(ukey), 3))
    np.add.at(cn, inv, nrm_u)
    cn /= np.maximum(np.linalg.norm(cn, axis=1, keepdims=True), 1e-9)

    best_s = np.zeros(n)
    best_d = np.zeros(n)
    for d in np.arange(D_MIN, D_MAX + 1e-9, D_STEP):
        for sgn in (1.0, -1.0):
            pc = np.floor((xyz + sgn * d * nrm - lo) / CELL_M).astype(np.int64)
            pk = (pc[:, 0] * ny + pc[:, 1]) * nz + pc[:, 2]
            pos = np.clip(np.searchsorted(ukey, pk), 0, len(ukey) - 1)
            hit = ukey[pos] == pk
            if not hit.any():
                continue
            score = np.abs(np.einsum("ij,ij->i", nrm_u[hit], cn[pos[hit]]))
            hi = np.where(hit)[0]
            sel = score > best_s[hi]
            best_s[hi[sel]] = score[sel]
            best_d[hi[sel]] = d

    ok = best_s > _MIN_SCORE
    return np.column_stack([np.where(ok, best_s, 0.0),
                            np.where(ok, best_d / D_MAX, 0.0)]).astype(np.float32)

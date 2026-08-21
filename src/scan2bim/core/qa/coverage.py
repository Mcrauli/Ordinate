"""Seinäkattavuus pilven omista pystypinnoista — ilman ground truthia.

Tämä on ainoa laatumittari joka toimii asiakkaan skannilla: labeleita ei ole
eikä tule. Sitä käytetään kahteen asiaan — ajojen vertailuun (`data/_matrix.py`)
ja putken sisällä siihen, että detektori VALITAAN mittaamalla eikä
arvaamalla rakennuksen koosta.

Mitä mitataan: piste on seinäpintaa kun sen normaali on vaakasuora JA sen
XY-solussa on pystypintaa yli puolet kaistan korkeudesta. Jälkimmäinen ehto
erottaa seinän hyllystä ja tavarasta, jotka ovat yhtä pystysuoria mutta eivät
jatku lattiasta kattoon.

Validoitu Rohbau3D:n GT:tä vasten (viisi sceneä): 0.951/0.852/0.894/0.507/0.606
kun GT antaa 0.887/0.863/0.860/0.807/0.752. Kolme osuu 0.06:n sisään; kaksi
eroaa koska mittari laskee työmaatavaran pystypinnaksi ja malli jättää sen
oikein pois. Siksi absoluuttinen taso EI ole vertailukelpoinen kohteiden
välillä — mittari on SAMAN pilven kahden ajon vertailuun, ja juuri siihen sitä
tässä käytetään.
"""
from __future__ import annotations

import numpy as np

_VOXEL = 50.0          # mm — detektorivalintaan riittää karkea pilvi
_NORMAL_KNN = 24
_VERT_NZ = 0.35        # |nz| tätä pienempi = pystypinta
_CELL = 200.0          # mm — XY-solu pystyjatkuvuuden mittaukseen
_SPAN_FRAC = 0.50      # solun pystypintojen z-välin oltava tämä osuus kaistasta
_MIN_CELL_PTS = 8
_BAND = 80.0           # mm — kaista mallin seinäpinnan ympärillä
_MIN_WALL_LEN = 800.0  # mm


def wallish_points(pts: np.ndarray, z_lo: float, z_hi: float,
                   voxel: float = _VOXEL) -> tuple[np.ndarray, np.ndarray]:
    """Seinämäiset pystypintapisteet kaistassa [z_lo, z_hi] ja niiden pilvi."""
    import open3d as o3d  # noqa: PLC0415

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    pc = pc.voxel_down_sample(voxel)
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=_NORMAL_KNN))
    q = np.asarray(pc.points)
    if len(q) == 0:
        return np.zeros(0, dtype=bool), q

    nz = np.abs(np.asarray(pc.normals)[:, 2])
    vert = (q[:, 2] > z_lo) & (q[:, 2] < z_hi) & (nz < _VERT_NZ)
    if not vert.any():
        return np.zeros(len(q), dtype=bool), q

    ij = np.floor(q[:, :2] / _CELL).astype(np.int64)
    key = ij[:, 0].astype(np.int64) * 10_000_000 + ij[:, 1]
    kv, zv = key[vert], q[vert, 2]
    order = np.argsort(kv, kind="stable")
    kv, zv = kv[order], zv[order]
    cuts = np.flatnonzero(np.diff(kv)) + 1
    need = _SPAN_FRAC * (z_hi - z_lo)
    good = [int(k) for k, g in zip(kv[np.concatenate([[0], cuts])], np.split(zv, cuts))
            if len(g) >= _MIN_CELL_PTS and (g.max() - g.min()) >= need]
    if not good:
        return np.zeros(len(q), dtype=bool), q
    return vert & np.isin(key, np.array(good, dtype=np.int64)), q


def wall_coverage(pts: np.ndarray, walls, floor_z: float, ceiling_z: float,
                  voxel: float = _VOXEL) -> float:
    """Osuus pilven seinäpinnoista jotka jokin mallin seinä kattaa.

    Palauttaa 0.0 kun pilvestä ei löydy seinäpintaa lainkaan — "ei mitattavaa"
    ei saa näyttää täydeltä kattavuudelta, koska silloin tyhjä malli voittaisi
    valinnan.
    """
    z_lo, z_hi = floor_z + 400.0, ceiling_z - 300.0
    if z_hi <= z_lo:
        return 0.0
    is_wall, q = wallish_points(pts, z_lo, z_hi, voxel)
    total = int(is_wall.sum())
    if total == 0:
        return 0.0

    xy = q[:, :2]
    claimed = np.zeros(len(q), dtype=bool)
    for w in walls:
        axis = getattr(w, "axis", None)
        if not axis or len(axis) < 2:
            continue
        a = np.asarray(axis[0], dtype=float)[:2]
        b = np.asarray(axis[-1], dtype=float)[:2]
        length = float(np.linalg.norm(b - a))
        if length < _MIN_WALL_LEN:
            continue
        u = (b - a) / length
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        half = float(getattr(w, "thickness", 0.0)) / 2.0
        claimed |= (s > 0) & (s < length) & (np.abs(np.abs(t) - half) < _BAND)
    return float((claimed & is_wall).sum()) / total

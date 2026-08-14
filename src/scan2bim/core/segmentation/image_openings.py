"""Kuvaohjattu aukkodetektio: E57:n kalibroiduista skannerikuvista (Matterport-
skybox / Radikal) tunnistetaan aukot geometrisella LÄPINÄKYVYYS-signaalilla.

Idea: rektifioi jokainen seinä lähimmän aseman panoraamasta seinätasolle ja
katso mihin skannerin säde näkee seinätason OHI (near > wall_dist) = aukko
(ikkuna/ovi/kulku). Maalattu umpiseinä = pisteet seinätasolla → ei aukko.
Okkluusio (kaluste/katto edessä, near < wall_dist) maskataan pois.

No-op ilman E57-kuvia → asunto/talo/PLY-putki muuttumaton (gauntlet-turvallinen).
Korkea tarkkuus (läpinäkyvyys on geometrinen totuus), rajattu kattavuus (vain
frontaalisti hyvin kuvantuvat seinät). Vain lisää aukkoja, ei poista.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from scan2bim.schemas.model import ElementSource, Opening, Wall


def _load_stations(e57_path: Path):
    """Skanneriasemien sijainnit (mm) kuvaposeista. [] jos tiedostossa ei ole kuvia.

    Pikseleitä EI dekoodata: päätös tehdään pistepilven syvyyspuskurista, joten
    kuvien sisältö ei vaikuta tulokseen mitenkään. Todennettu korvaamalla
    panoraama mustalla 4×8-kuvalla — sama aukko, samat mitat. Dekoodaus +
    panoraaman ompelu maksoi 15.2 s (`parking-lot-updated.e57`, 285 kuvaa).
    Kuvat toimivat siis vain asemien LÄHTEENÄ ja koko piirteen portt(e)ina.
    """
    import pye57
    f = pye57.E57(str(e57_path))
    root = f.root
    if "images2D" not in [c.elementName() for c in root]:
        return []
    im = root["images2D"]
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for i in range(len(im)):
        el = im[i]
        try:
            el["pinholeRepresentation"]      # sama kelpoisuusehto kuin ennen
            tr = el["pose"]["translation"]
            T = np.array([tr[k].value() for k in ("x", "y", "z")]) * 1000.0
        except Exception:  # noqa: BLE001,PERF203
            continue
        groups[tuple(np.round(T / 100).astype(int))].append(T)
    return [v[0] for v in groups.values()]


def _depthbuf(T, P, DH=256, DW=512):
    import cv2
    r = P - T; d = np.linalg.norm(r, axis=1); mk = d > 1
    lon = np.arctan2(r[mk, 1], r[mk, 0]); lat = np.arcsin(np.clip(r[mk, 2] / d[mk], -1, 1))
    ix = np.clip(((lon + np.pi) / (2 * np.pi) * DW).astype(int), 0, DW - 1)
    iy = np.clip(((np.pi / 2 - lat) / np.pi * DH).astype(int), 0, DH - 1)
    buf = np.full((DH, DW), np.inf, np.float32); np.minimum.at(buf, (iy, ix), d[mk])
    return cv2.erode(np.where(np.isfinite(buf), buf, 1e9).astype(np.float32), np.ones((5, 5), np.uint8))


def detect_image_openings(walls: list[Wall], e57_path: Path, cloud_pts: np.ndarray) -> list[Opening]:
    """Palauta kuvista tunnistetut aukot. [] jos ei kuvia / pillow puuttuu / virhe."""
    try:
        import cv2
        stations_raw = _load_stations(Path(e57_path))
    except Exception:  # noqa: BLE001
        return []
    if not stations_raw:
        return []
    P = np.asarray(cloud_pts, np.float32)
    if len(P) > 6_000_000:
        P = P[:: -(-len(P) // 6_000_000)]
    DH, DW = 256, 512
    stations = [(T, _depthbuf(T, P, DH, DW)) for T in stations_raw]

    out: list[Opening] = []
    for wi, w in enumerate(walls):
        if len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], float); p1 = np.array(w.axis[1], float)
        d = p1 - p0; L = float(np.linalg.norm(d))
        if L < 800:
            continue
        u = d / L; n = np.array([-u[1], u[0]]); cen = (p0 + p1) / 2
        z0 = w.z_min; z1 = z0 + w.height
        # lähin frontaali asema
        best = None
        for T, db in stations:
            v = cen - T[:2]; dist = float(np.linalg.norm(v))
            if dist < 300 or dist > 16000:
                continue
            cosang = abs(float(v @ n)) / dist
            if cosang < 0.6:
                continue
            score = cosang / (1 + dist / 8000)
            if best is None or score > best[0]:
                best = (score, T, db)
        if best is None:
            continue
        _, T, db = best
        mmpp = 20.0
        Wp = int(np.clip(L / mmpp, 80, 1400)); Hp = int(np.clip((z1 - z0) / mmpp, 60, 500))
        aa = np.linspace(0, L, Wp); zz = np.linspace(z1, z0, Hp); A, Z = np.meshgrid(aa, zz)
        X = p0[0] + A * u[0]; Y = p0[1] + A * u[1]
        ray = np.stack([X - T[0], Y - T[1], Z - T[2]], -1).reshape(-1, 3)
        wd = np.linalg.norm(ray, axis=1)
        lon = np.arctan2(ray[:, 1], ray[:, 0]); lat = np.arcsin(np.clip(ray[:, 2] / wd, -1, 1))
        dx = np.clip(((lon + np.pi) / (2 * np.pi) * DW).astype(int), 0, DW - 1)
        dy = np.clip(((np.pi / 2 - lat) / np.pi * DH).astype(int), 0, DH - 1)
        near = db[dy, dx].reshape(Hp, Wp); wdr = wd.reshape(Hp, Wp)
        occluded = near < wdr - 600
        seethru = near > wdr + 700
        solid = (~occluded) & (~seethru)
        if occluded.mean() > 0.6 or solid.mean() < 0.15:
            continue
        cand = seethru.astype(np.uint8) * 255
        cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
        cnts, _ = cv2.findContours(cand, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, ww, hh = cv2.boundingRect(c); area = cv2.contourArea(c)
            if area / (ww * hh) < 0.55:
                continue
            wmm = ww * mmpp; hmm = hh * mmpp; ar = ww / max(hh, 1)
            if wmm < 500 or hmm < 500 or wmm > 4000 or hmm > 3200 or ar > 4 or ar < 0.25:
                continue
            along0 = x * mmpp
            sill = max((z1 - (y + hh) * mmpp) - z0, 0.0)
            otype = "window" if sill > 500 else "door"
            out.append(Opening(
                id=f"img_open_{wi}_{len(out)}", confidence=0.55,
                source=ElementSource(method="opening", notes="image-seethru"),
                opening_type=otype, wall_id=w.id, position_along=float(along0),
                width=float(wmm), sill_height=float(sill), opening_height=float(hmm),
            ))
    return out

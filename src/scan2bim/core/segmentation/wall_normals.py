"""Seinät pystypinnoista: normaalien suunta → tasot → segmentit.

`wall_contour` lähtee lattiasta ja `wall_histogram` pohjan tiheysprojektiosta.
Molemmat olettavat että lattia näkyy ja että pohja on avoin. Matalassa
sokkeloisessa kellarissa kumpikaan ei päde — mitattu koulun kellarilla
(5697 m², vapaa korkeus 1.8 m): histogrammi kattoi pilven pystypinnoista
0.009 ja contour 0.045, kun tämä menetelmä kattoi 0.460 ja piirsi
tunnistettavan pohjapiirroksen koko rakennuksesta.

Tämä lähtee siitä mikä seinässä on mitattavaa: pystysuora pinta joka jatkuu
lattiasta kattoon. Manhattan-oletusta ei ole — suunnat luetaan normaalien
kulmahistogrammista, joten vinot seinät kelpaavat.

Menetelmä löytää myös palkkilinjat ja pilaririvit, koska nekin ovat
pystypintoja: Rohbau scene_07004 (avoin työmaahalli) sai kaksi pitkää
valeseinää keskelle hallia. Niitä EI yritetä karsia täällä — putken
semantics-ketju (`prune_unsupported_walls`, jatkuvuus, tuki) on rakennettu
juuri siihen, ja sama karsinta hoitaa histogrammidetektorin palkkilinjat.
Detektorin tehtävä on löytää ehdokkaat, ei tuomita niitä.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

from scan2bim.core.segmentation.base import DetectorRegistry, ElementDetector
from scan2bim.schemas.model import ElementSource, StructuralModel, Wall

_VOXEL = 25.0
_NORMAL_KNN = 30
_VERT_NZ = 0.35        # |nz| tätä pienempi = pystypinta
_DIR_BIN_DEG = 2.0
_DIR_MIN_FRAC = 0.04   # suunnan massa osuutena vahvimmasta suunnasta
_DIR_TOL_DEG = 6.0
_OFF_BIN = 25.0        # mm — etäisyyshistogrammin bini
_PLANE_BAND = 45.0     # mm — kaista tason ympärillä
_GAP_MM = 700.0        # mm — tätä pidempi aukko katkaisee segmentin
_MIN_LEN = 900.0       # mm
_SPAN_FRAC = 0.45      # segmentin z-välin oltava tämä osuus kaistasta
_SPAN_CAP = 2400.0     # mm — mutta ei koskaan tätä enempää (ks. _need_span)
_MIN_PTS = 60
_PAIR_MIN, _PAIR_MAX = 80.0, 500.0    # mm — vastakkaisen pinnan etäisyys
_OVERLAP_FRAC = 0.40   # osuus lyhyemmästä: näin paljon päällekkäin = sama seinä
_THICK_DEFAULT = 200.0
_BAND_LO, _BAND_HI = 400.0, 300.0     # mm — kaista lattian yläpuolelta katon alle


@DetectorRegistry.register("normals")
class NormalsWallDetector(ElementDetector):
    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        model = StructuralModel()
        pts = np.asarray(cloud.points)
        if len(pts) < 1000:
            return model

        q, nrm = _prepare(pts)
        floor = float(np.percentile(q[:, 2], 2))
        ceiling = float(np.percentile(q[:, 2], 98))
        z_lo, z_hi = floor + _BAND_LO, ceiling - _BAND_HI
        if z_hi <= z_lo:
            return model

        band = (q[:, 2] > z_lo) & (q[:, 2] < z_hi)
        vert = band & (np.abs(nrm[:, 2]) < _VERT_NZ)
        if vert.sum() < _MIN_PTS:
            return model

        ang = np.degrees(np.arctan2(nrm[:, 1], nrm[:, 0])) % 180.0
        for deg in _directions(ang[vert]):
            d = np.abs((ang - deg + 90.0) % 180.0 - 90.0)
            sel = vert & (d < _DIR_TOL_DEG)
            if sel.sum() < _MIN_PTS:
                continue
            for s in _pair_faces(_segments(q, sel, deg, z_lo, z_hi), deg):
                model.walls.append(Wall(
                    id=f"wall_n_{len(model.walls):03d}",
                    confidence=1.0,
                    classification="wall",
                    source=ElementSource(method="normals"),
                    axis=[[float(s["a"][0]), float(s["a"][1])],
                          [float(s["b"][0]), float(s["b"][1])]],
                    height=float(ceiling - floor),
                    thickness=round(float(s["thick"]), 1),
                    z_min=float(floor),
                ))
        return model


def _prepare(pts: np.ndarray):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    pc = pc.voxel_down_sample(_VOXEL)
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=_NORMAL_KNN))
    return np.asarray(pc.points), np.asarray(pc.normals)


def _directions(ang: np.ndarray) -> list[float]:
    """Dominantit seinäsuunnat asteina [0,180) — kulmahistogrammin huiput."""
    nb = int(180.0 / _DIR_BIN_DEG)
    hist, edges = np.histogram(ang, bins=nb, range=(0.0, 180.0))
    if not hist.max():
        return []
    centers = 0.5 * (edges[:-1] + edges[1:])
    rolled = np.concatenate([hist[-3:], hist, hist[:3]])
    out = []
    for i in range(3, len(rolled) - 3):
        if rolled[i] == rolled[i - 3:i + 4].max() and rolled[i] >= _DIR_MIN_FRAC * hist.max():
            out.append(float(centers[i - 3]))
    return out


def _need_span(z_lo: float, z_hi: float) -> float:
    """Kuinka korkealle segmentin on yletyttävä ollakseen seinä.

    Portin tehtävä on erottaa seinä hyllynreunasta ja putkesta: ilman sitä
    tarkkuus romahtaa 0.725 → 0.318 (`data/_normals_span_rule.py`, viisi
    Rohbau-sceneä GT:tä vasten). Portti siis tarvitaan.

    Vaatimus oli aiemmin pelkkä `_SPAN_FRAC * (z_hi - z_lo)` — osuus koko
    rakennuksen kaistasta. Se on TASO EIKÄ SUHDE samalla tavalla kuin
    `wall_histogram`in entinen globaali piikkikynnys: 10 m runkohallissa se
    vaatii seinältä 4.05 m korkeutta, jolloin 2–4 m väliseinä on mahdoton
    riippumatta siitä onko se oikea seinä. Mitattuna GT-instansseista löytyi
    2–4 m luokasta 0.19 ja 1–2 m luokasta 0.05.

    Katkaisu poistaa juuri sen: vaatimus lakkaa kasvamasta katonkorkeuden
    mukana. Matalassa tilassa `_SPAN_FRAC * kaista` on pienempi ja sääntö on
    täsmälleen entinen — katkaisu puree vasta kun vapaa korkeus ylittää
    ~6.5 m, joten sääntö ei voi olla missään entistä TIUKEMPI.

    Mitattu viidellä Rohbau-scenellä (GT-instanssikattavuus / tarkkuus / F1):

        nykyinen           0.316 / 0.725 / 0.435
        _SPAN_FRAC 0.20    0.783 / 0.619 / 0.687
        katkaisu 2400 mm   0.768 / 0.846 / **0.804**

    Kaksi käsitteellistä vaihtoehtoa mitattiin ja kumottiin: lattiakosketus
    ("seinä seisoo lattialla") F1 0.555 ja aspektisuhde (korkeus suhteessa
    omaan pituuteen) F1 0.524 — kumpikin selvästi huonompi kuin katkaisu.

    Korkeus millimetreinä on rakennuksen ominaisuus eikä skannin: toisin kuin
    kielletyt pistekynnykset se ei riipu pistetiheydestä.
    """
    return min(_SPAN_CAP, _SPAN_FRAC * (z_hi - z_lo))


def _segments(q: np.ndarray, sel: np.ndarray, deg: float,
              z_lo: float, z_hi: float) -> list[dict]:
    """Yhden suunnan seinätasot ja niiden pituussuuntaiset segmentit."""
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy, z = q[sel][:, :2], q[sel][:, 2]
    off = xy @ n
    nb = max(int((off.max() - off.min()) / _OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

    need_span = _need_span(z_lo, z_hi)
    out: list[dict] = []
    for i in peaks:
        c = float(centers[i])
        m = np.abs(off - c) < _PLANE_BAND
        if m.sum() < _MIN_PTS:
            continue
        t, zz = xy[m] @ u, z[m]
        order = np.argsort(t)
        t, zz = t[order], zz[order]
        cuts = np.flatnonzero(np.diff(t) > _GAP_MM) + 1
        for pt, pz in zip(np.split(t, cuts), np.split(zz, cuts)):
            if len(pt) < _MIN_PTS or float(pt[-1] - pt[0]) < _MIN_LEN:
                continue
            if float(pz.max() - pz.min()) < need_span:
                continue
            out.append({"offset": c, "a": n * c + u * float(pt[0]),
                        "b": n * c + u * float(pt[-1]), "n": int(len(pt))})
    return out


def _pair_faces(segs: list[dict], deg: float) -> list[dict]:
    """Yhdistä seinän KAKSI PINTAA yhdeksi seinäksi, akseli keskelle.

    Ilman tätä jokainen seinä tulee malliin kahdesti ja kummankin akseli on
    pinnalla — mittauskaista osuu silloin seinän sisään tai ilmaan.
    """
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    for s in segs:
        s["t0"] = float(min(s["a"] @ u, s["b"] @ u))
        s["t1"] = float(max(s["a"] @ u, s["b"] @ u))
    segs = sorted(segs, key=lambda s: -(s["t1"] - s["t0"]))

    used: set[int] = set()
    out: list[dict] = []
    for i, s in enumerate(segs):
        if i in used:
            continue
        best, best_gap = None, None
        for j, o in enumerate(segs):
            if j <= i or j in used:
                continue
            gap = abs(o["offset"] - s["offset"])
            if not (_PAIR_MIN <= gap <= _PAIR_MAX):
                continue
            lo, hi = max(s["t0"], o["t0"]), min(s["t1"], o["t1"])
            shorter = min(s["t1"] - s["t0"], o["t1"] - o["t0"])
            if shorter <= 0 or (hi - lo) < _OVERLAP_FRAC * shorter:
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = j, gap
        if best is None:
            out.append({**s, "thick": _THICK_DEFAULT})
            continue
        o = segs[best]
        used.add(best)
        mid = 0.5 * (s["offset"] + o["offset"])
        t0, t1 = max(s["t0"], o["t0"]), min(s["t1"], o["t1"])
        out.append({"a": n * mid + u * t0, "b": n * mid + u * t1,
                    "n": s["n"] + o["n"], "thick": best_gap, "t0": t0, "t1": t1})
    return [w for w in out if (w["t1"] - w["t0"]) >= _MIN_LEN]

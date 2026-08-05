"""Deterministinen tiheyshistogrammi-seinädetektori (Manhattan-oletus).

RANSAC (open3d.segment_plane) on epädeterministinen (OpenMP-säie-tie → sama skanni
antaa eri seinämäärän ajojen välillä) JA hidas isossa pilvessä (~130 s), JA sen
kallistuneet tasot nappaavat pilarilinjoja kontaminoiden seinät.

Tämä detektori on deterministinen, ~300× nopeampi ja pilarivapaa: rakennuksen
seinät ovat lähes kaikki kahden kohtisuoran pääsuunnan mukaisia. Kierrä pilvi
pääsuuntiin, ota keskikorkeuden viipale (ei lattiaa/kattoa), ja histogrammoi
kumpikin akseli — seinä on histogrammipiikki (vakio x tai y). Piikkiparit
(≤MAX_THICKNESS erillään) ovat saman seinän kaksi pintaa → paksuus suoraan.
Seinän jänne mitataan tiheimmästä yhtäjaksoisesta ajosta (ei min/max → ei
venymää tyhjän lattian/laatan yli). Vinot seinät (harvinaisia) jäävät löytymättä
— käytä silloin ``ransac``-detektoria.
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import ElementSource, Metadata, StructuralModel, Wall

from .base import DetectorRegistry, ElementDetector

_MID_LO = 0.25              # keskikorkeusviipale: vain seinäpinta, ei lattia/katto
_MID_HI = 0.75
_BIN = 20.0                # mm — seinäpiikin histogrammiresoluutio
_PEAK_SIGMA = 3.0          # piikki = keskiarvo + tämä × keskihajonta
_PEAK_MIN_PTS = 50         # min pisteitä binissä jotta se on seinä
_MAX_THICKNESS = 500.0     # mm — kaksi pintaa tätä lähempänä = sama seinä
_DEFAULT_THICKNESS = 200.0 # mm — yksipuolisen (ulkoseinä) oletuspaksuus
_MIN_WALL_LENGTH = 2000.0  # mm — lyhyempi piikki ei ole seinä
_DENSE_BIN = 200.0         # mm — jänteen dense-run-bini
_DENSE_GAP_BRIDGE = 1600.0 # mm — ovi/ikkuna-aukot sillataan jänteessä
_MIN_WALL_HEIGHT = 1500.0  # mm — matalampi tila hylätään (ei seinää)


@DetectorRegistry.register("histogram")
class WallDetectorHistogram(ElementDetector):
    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        pts = np.asarray(cloud.points)
        walls: list[Wall] = []
        if len(pts) >= 100:
            z = pts[:, 2]
            z_min = float(z.min())
            height = float(z.max() - z_min)
            if height >= _MIN_WALL_HEIGHT:
                mid = pts[(z > z_min + _MID_LO * height) & (z < z_min + _MID_HI * height)]
                if len(mid) >= 100:
                    walls = self._detect_walls(mid[:, :2], z_min, height)
        model = StructuralModel(walls=walls)
        model.metadata = Metadata(detector_method="histogram")
        return model

    def _detect_walls(self, xy: np.ndarray, z_min: float, height: float) -> list[Wall]:
        theta = _dominant_angle(xy)
        c, s = np.cos(-theta), np.sin(-theta)
        rot = xy @ np.array([[c, -s], [s, c]]).T   # kierrä pääsuuntiin
        lo = rot.min(axis=0)
        hi = rot.max(axis=0)

        raw: list[tuple[np.ndarray, np.ndarray, float]] = []
        # akseli 0 = pystyt (vakio x, jänne y); akseli 1 = vaakat (vakio y, jänne x)
        for a in (0, 1):
            o = 1 - a
            for pos, e0, e1, thick in _build_axis_walls(
                rot[:, a], rot[:, o], lo[a], hi[a], lo[o], hi[o]
            ):
                p0 = np.empty(2); p1 = np.empty(2)
                p0[a] = pos; p1[a] = pos
                p0[o] = e0; p1[o] = e1
                raw.append((p0, p1, thick))

        # kierrä akselit takaisin maailmankoordinaatteihin
        cb, sb = np.cos(theta), np.sin(theta)
        R = np.array([[cb, -sb], [sb, cb]])
        walls: list[Wall] = []
        for i, (p0, p1, thick) in enumerate(raw):
            w0 = R @ p0
            w1 = R @ p1
            walls.append(Wall(
                id=f"wall_{i:03d}",
                confidence=1.0,
                classification="wall",
                source=ElementSource(method="histogram", notes="density-peak"),
                axis=[[round(float(w0[0]), 1), round(float(w0[1]), 1)],
                      [round(float(w1[0]), 1), round(float(w1[1]), 1)]],
                height=round(height, 1),
                thickness=round(thick, 1),
                z_min=round(z_min, 1),
            ))
        return walls


def _dominant_angle(xy: np.ndarray) -> float:
    """Kulma [0, π/2) joka kohdistaa seinät akseleille. Testaa kandidaatit ja
    maksimoi histogrammien "piikkisyys" (Σ count²): kohdistettuna seinät
    tiivistyvät harvoihin bineihin → suurin neliösumma. Deterministinen."""
    sample = xy if len(xy) <= 200_000 else xy[:: len(xy) // 200_000 + 1]
    best_theta, best_score = 0.0, -1.0
    for coarse in np.arange(0.0, 90.0, 2.0):
        sc = _alignment_score(sample, np.radians(coarse))
        if sc > best_score:
            best_score, best_theta = sc, coarse
    # tarkennus ±2° 0.25° askelin
    for fine in np.arange(best_theta - 2.0, best_theta + 2.0, 0.25):
        sc = _alignment_score(sample, np.radians(fine))
        if sc > best_score:
            best_score, best_theta = sc, fine
    return float(np.radians(best_theta % 90.0))


def _alignment_score(xy: np.ndarray, theta: float) -> float:
    c, s = np.cos(-theta), np.sin(-theta)
    rot = xy @ np.array([[c, -s], [s, c]]).T
    score = 0.0
    for a in (0, 1):
        v = rot[:, a]
        nb = max(int((v.max() - v.min()) / 100.0), 1)   # 100mm karkea bini riittää
        hist, _ = np.histogram(v, bins=nb)
        h = hist.astype(np.float64) / max(len(v), 1)
        score += float(np.sum(h * h))
    return score


def _build_axis_walls(coord, other, clo, chi, olo, ohi):
    """Etsi seinälinjat coord-akselilta; yhdistä vastakkaiset pinnat; jänne dense-run."""
    peaks = _peaks_1d(coord, clo, chi)
    used = [False] * len(peaks)
    out = []
    for i, (pos, _n) in enumerate(peaks):
        if used[i]:
            continue
        partner = next((j for j in range(i + 1, len(peaks))
                        if not used[j] and abs(peaks[j][0] - pos) <= _MAX_THICKNESS), None)
        if partner is not None:
            pos2 = peaks[partner][0]
            axis_pos = (pos + pos2) / 2.0
            thick = abs(pos2 - pos)
            used[partner] = True
            band_lo, band_hi = min(pos, pos2) - _BIN, max(pos, pos2) + _BIN
        else:
            axis_pos = pos
            thick = _DEFAULT_THICKNESS
            band_lo, band_hi = pos - 100.0, pos + 100.0
        used[i] = True
        m = (coord >= band_lo) & (coord <= band_hi)
        e0, e1 = _dense_run(other[m], olo, ohi)
        if e1 - e0 >= _MIN_WALL_LENGTH:
            out.append((axis_pos, e0, e1, thick))
    return out


def _peaks_1d(coord, lo, hi):
    nb = int((hi - lo) / _BIN) + 1
    if nb < 1:
        return []
    hist, edges = np.histogram(coord, bins=nb, range=(lo, hi))
    thr = max(hist.mean() + _PEAK_SIGMA * hist.std(), float(_PEAK_MIN_PTS))
    over = hist >= thr
    out = []
    i = 0
    while i < nb:
        if over[i]:
            j = i
            while j < nb and over[j]:
                j += 1
            out.append(((edges[i] + edges[j]) / 2.0, int(hist[i:j].sum())))
            i = j
        else:
            i += 1
    return out


def _dense_run(vals, lo, hi):
    if len(vals) == 0:
        return lo, hi
    lo, hi = float(vals.min()), float(vals.max())
    span = hi - lo
    if span < _DENSE_BIN:
        return lo, hi
    nb = max(int(span / _DENSE_BIN), 1)
    hist, edges = np.histogram(vals, bins=nb, range=(lo, hi))
    nz = hist[hist > 0]
    thr = max(3.0, 0.25 * float(np.median(nz)))
    occ = np.flatnonzero(hist >= thr)
    if occ.size == 0:
        return lo, hi
    gap = max(int(_DENSE_GAP_BRIDGE / (span / nb)), 1)
    best_n, bs, be = -1, occ[0], occ[-1]
    start = prev = occ[0]
    for k in list(occ[1:]) + [None]:
        if k is None or k - prev > gap:
            n = int(hist[start:prev + 1].sum())
            if n > best_n:
                best_n, bs, be = n, start, prev
            if k is not None:
                start = k
        if k is not None:
            prev = k
    return float(edges[bs]), float(edges[be + 1])

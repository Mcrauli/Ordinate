"""
Hough-muunnosperustainen deterministinen seinädetektio.

Algoritmi:
  1. XY-pisteet projisoidaan kaikkiin suuntiin 0–180° (2° karkea askel)
  2. Projektiivistoogrammeista löydetään dominantit seinäsuunnat (max 8)
  3. Kukin suunta tarkennetaan 1° välein
  4. Jokaiselle suunnalle: 5mm histogrammi → seinäpinnat
  5. Globaali ahne paritus: score=(h_i+h_j)/etäisyys → oikeat pinnat pariksi
  6. Inlier-pisteet molemmilta pinnoilta → SVD-akseli + paksuus
"""
from __future__ import annotations

import math
import numpy as np
import open3d as o3d
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from scan2bim.schemas.model import ElementSource, Metadata, StructuralModel, Wall
from scan2bim.core.segmentation.base import DetectorRegistry, ElementDetector

_MIN_INLIERS = 200           # min inlier-pisteitä per seinäpari
_MIN_WALL_HEIGHT = 1500.0    # mm
_MIN_WALL_LENGTH = 600.0     # mm
_MIN_THICKNESS = 50.0        # mm — ohut lasiseinä ~66mm
_MAX_THICKNESS = 450.0       # mm

_COARSE_STEP_DEG = 2.0
_ANGLE_BIN_DEG = 1.0
_ANGLE_MERGE_DEG = 8.0
_MAX_DIRECTIONS = 6

_DIST_BIN_MM = 1.0           # seinäpinnan paikkatarkkuus mm
_DIST_SMOOTH_BINS = 3
_DIST_MIN_PEAK_MM = 40.0     # min etäisyys huippujen välillä
_PLANE_DIST_MM = 3.0         # inlier-toleranssi seinäpinnalta
_RUN_BIN_MM = 150.0          # seinänpätkien segmentoinnin rasterointi akselilla
_RUN_GAP_MM = 600.0          # tätä pidempi tyhjä jakso katkaisee seinän

_Z_SKIP_FRAC = 0.07


@DetectorRegistry.register("normals")
class NormalAssistedDetector(ElementDetector):
    """Hough-muunnosperustainen deterministinen seinädetektori."""

    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        # Suunta- ja pintahaku ovat robusteja harvennukselle, ja seinät tarkennetaan
        # silti täydestä pilvestä (recenter/trim pipelinessä). Iso pilvi tekee Hough-
        # hausta hitaan (90 kulmaa × N), joten kapataan ~800k pisteeseen.
        if len(cloud.points) > 800_000:
            voxel = 20.0
            work = cloud.voxel_down_sample(voxel)
            while len(work.points) > 800_000 and voxel < 120.0:
                voxel *= 1.4
                work = cloud.voxel_down_sample(voxel)
            pts_all = np.asarray(work.points)
        else:
            pts_all = np.asarray(cloud.points)
        if len(pts_all) < 500:
            return StructuralModel()

        walls = _extract_walls_hough(pts_all)
        model = StructuralModel(walls=walls)
        model.metadata = Metadata(detector_method="normals")
        return model


def _extract_walls_hough(pts: np.ndarray) -> list[Wall]:
    z = pts[:, 2]
    z_range = float(z.max() - z.min())
    skip = z_range * _Z_SKIP_FRAC
    wall_mask = (z >= float(z.min()) + skip) & (z <= float(z.max()) - skip)
    wall_pts = pts[wall_mask]

    if len(wall_pts) < _MIN_INLIERS * 2:
        return []

    xy = wall_pts[:, :2].astype(np.float32)

    # Vaihe 1: karkea suuntahaku
    coarse_angles = np.arange(0.0, 180.0, _COARSE_STEP_DEG)
    scores = []
    min_d_coarse = max(int(_DIST_MIN_PEAK_MM / _DIST_BIN_MM), 2)
    for a in coarse_angles:
        rad = np.radians(a)
        n = np.array([np.cos(rad), np.sin(rad)], dtype=np.float32)
        proj = xy @ n
        p_min, p_max = float(proj.min()), float(proj.max())
        n_bins = max(int((p_max - p_min) / _DIST_BIN_MM), 4)
        hist, _ = np.histogram(proj, bins=n_bins, range=[p_min, p_max])
        smooth = uniform_filter1d(hist.astype(float), size=3)
        pks, _ = find_peaks(smooth, height=_MIN_INLIERS * 0.3, distance=min_d_coarse)
        score = float(smooth[pks].max()) if len(pks) > 0 else 0.0
        scores.append((score, float(a)))

    scores.sort(reverse=True)

    dominant: list[float] = []
    for score, a in scores:
        if score == 0.0:
            break
        if not any(abs(((a - d + 90.0) % 180.0) - 90.0) < _ANGLE_MERGE_DEG for d in dominant):
            dominant.append(a)
        if len(dominant) >= _MAX_DIRECTIONS:
            break

    if not dominant:
        return []

    # Vaihe 2: tarkennettu suuntahaku
    refined: list[float] = []
    for a_center in dominant:
        best_score, best_a = 0.0, a_center
        for a in np.arange(a_center - _COARSE_STEP_DEG, a_center + _COARSE_STEP_DEG + 0.5, _ANGLE_BIN_DEG):
            a_mod = float(a % 180.0)
            rad = np.radians(a_mod)
            n = np.array([np.cos(rad), np.sin(rad)], dtype=np.float32)
            proj = xy @ n
            p_min, p_max = float(proj.min()), float(proj.max())
            n_bins = max(int((p_max - p_min) / _DIST_BIN_MM), 4)
            hist, _ = np.histogram(proj, bins=n_bins, range=[p_min, p_max])
            smooth = uniform_filter1d(hist.astype(float), size=3)
            pks, _ = find_peaks(smooth, height=_MIN_INLIERS * 0.3, distance=min_d_coarse)
            sc = float(smooth[pks].max()) if len(pks) > 0 else 0.0
            if sc > best_score:
                best_score, best_a = sc, a_mod
        refined.append(best_a)

    # Vaihe 3: seinäparit kullekin suunnalle
    walls: list[Wall] = []
    for a in refined:
        walls.extend(_walls_for_direction(wall_pts, a, len(walls)))

    return walls


def _robust_line_normal(xy: np.ndarray, iters: int = 5) -> np.ndarray | None:
    """IRLS-robusti suoran (pystyseinäpinnan) normaali XY:ssä. Cauchy-painot → outlier-kesto."""
    if len(xy) < 3:
        return None
    c = xy.mean(axis=0)
    d = xy - c
    try:
        _, _, vt = np.linalg.svd(d, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    n = vt[-1]  # pienimmän varianssin suunta = normaali
    for _ in range(iters):
        r = (xy - c) @ n
        med = float(np.median(r))
        scale = 1.4826 * float(np.median(np.abs(r - med))) + 1e-6
        w = 1.0 / (1.0 + (r / (2.0 * scale)) ** 2)
        wsum = float(w.sum())
        if wsum < 1e-9:
            break
        c = (xy * w[:, None]).sum(axis=0) / wsum
        dd = xy - c
        cov = (dd * w[:, None]).T @ dd
        evals, evecs = np.linalg.eigh(cov)
        n = evecs[:, 0]
    nlen = float(np.linalg.norm(n))
    return n / nlen if nlen > 1e-9 else None


def _walls_for_direction(wall_pts: np.ndarray, angle_deg: float, id_offset: int) -> list[Wall]:
    """Löytää kaikki seinäparit annetussa suunnassa globaalilla ahneparituksella."""
    rad = np.radians(angle_deg)
    n2d = np.array([np.cos(rad), np.sin(rad)], dtype=np.float64)

    proj_n = wall_pts[:, :2] @ n2d

    p_min, p_max = float(proj_n.min()), float(proj_n.max())
    n_bins = max(int((p_max - p_min) / _DIST_BIN_MM), 8)
    hist, edges = np.histogram(proj_n, bins=n_bins, range=[p_min, p_max])
    smooth = uniform_filter1d(hist.astype(float), size=_DIST_SMOOTH_BINS)
    centers = 0.5 * (edges[:-1] + edges[1:])

    min_d = max(int(_DIST_MIN_PEAK_MM / _DIST_BIN_MM), 2)
    peaks, _ = find_peaks(smooth, height=_MIN_INLIERS * 0.4, distance=min_d)

    if len(peaks) < 2:
        return []

    peak_pos = [float(centers[p]) for p in peaks]
    peak_h = [float(smooth[p]) for p in peaks]

    # Globaali ahne paritus: score = (h_i + h_j) / etäisyys → suositaan lähimpiä vahvoja pareja
    all_pairs: list[tuple[float, int, int, float]] = []
    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            dist = abs(peak_pos[i] - peak_pos[j])
            if _MIN_THICKNESS <= dist <= _MAX_THICKNESS:
                score = (peak_h[i] + peak_h[j]) / (dist ** 1.5)
                all_pairs.append((score, i, j, dist))

    all_pairs.sort(reverse=True)

    used: set[int] = set()
    chosen: list[tuple[int, int, float]] = []
    for score, i, j, dist in all_pairs:
        if i in used or j in used:
            continue
        used.add(i)
        used.add(j)
        chosen.append((i, j, dist))

    walls_out: list[Wall] = []
    for i, j, thickness in chosen:
        d1, d2 = peak_pos[i], peak_pos[j]

        inlier_mask = (np.abs(proj_n - d1) < _PLANE_DIST_MM) | (np.abs(proj_n - d2) < _PLANE_DIST_MM)
        inlier_pts = wall_pts[inlier_mask]

        if len(inlier_pts) < _MIN_INLIERS:
            continue

        z_extent = float(inlier_pts[:, 2].max() - inlier_pts[:, 2].min())
        if z_extent < _MIN_WALL_HEIGHT:
            continue

        # Robusti per-pinta -sovitus (IRLS): kumpikin seinäpinta erikseen →
        # outlier-kestävä normaali ja paksuus. Pinnat ovat pystyjä → työ XY:ssä.
        xy1 = wall_pts[np.abs(proj_n - d1) < _PLANE_DIST_MM, :2]
        xy2 = wall_pts[np.abs(proj_n - d2) < _PLANE_DIST_MM, :2]
        if len(xy1) < _MIN_INLIERS // 2 or len(xy2) < _MIN_INLIERS // 2:
            continue

        n1 = _robust_line_normal(xy1)
        n2 = _robust_line_normal(xy2)
        if n1 is None or n2 is None:
            continue
        if float(np.dot(n1, n2)) < 0:
            n2 = -n2
        pn_xy = n1 + n2
        pn_len = float(np.linalg.norm(pn_xy))
        if pn_len < 1e-6:
            continue
        pn_xy /= pn_len
        if float(np.dot(pn_xy, n2d)) < 0:
            pn_xy = -pn_xy

        along_svd = np.array([-pn_xy[1], pn_xy[0]])

        # Pintojen etäisyydet normaalin suunnassa (mediaani = robusti)
        d1m = float(np.median(xy1 @ pn_xy))
        d2m = float(np.median(xy2 @ pn_xy))
        center_d = 0.5 * (d1m + d2m)
        thickness = abs(d1m - d2m)
        if not (_MIN_THICKNESS <= thickness <= _MAX_THICKNESS):
            continue

        # Pilko suunta todellisiksi seinänpätkiksi: yksi (suunta, etäisyyspari) voi
        # osua moneen erilliseen seinään / ylittää tyhjää. Histogrammi akselilla,
        # tiheät yhtenäiset jaksot = seinät (>_RUN_GAP_MM tyhjä katkaisee).
        proj_a_svd = inlier_pts[:, :2] @ along_svd
        a_lo, a_hi = float(proj_a_svd.min()), float(proj_a_svd.max())
        nb = max(int((a_hi - a_lo) / _RUN_BIN_MM) + 1, 1)
        counts, edges = np.histogram(proj_a_svd, bins=nb, range=(a_lo, a_hi))
        nz = counts[counts > 0]
        if len(nz) == 0:
            continue
        occ = counts >= max(2.0, 0.12 * float(np.median(nz)))
        gap_bins = max(int(_RUN_GAP_MM / _RUN_BIN_MM), 1)

        bi = 0
        while bi < nb:
            if not occ[bi]:
                bi += 1
                continue
            last = bi
            gap = 0
            bj = bi
            while bj < nb:
                if occ[bj]:
                    last = bj
                    gap = 0
                else:
                    gap += 1
                    if gap > gap_bins:
                        break
                bj += 1
            a = float(edges[bi])
            b = float(edges[last + 1])
            bi = bj
            seg_len = b - a
            if seg_len < _MIN_WALL_LENGTH:
                continue
            nseg = int(((proj_a_svd >= a) & (proj_a_svd <= b)).sum())
            if nseg < _MIN_INLIERS // 2:
                continue
            mid = (a + b) / 2.0
            p0 = (mid - seg_len / 2.0) * along_svd + center_d * pn_xy
            p1 = (mid + seg_len / 2.0) * along_svd + center_d * pn_xy
            walls_out.append(Wall(
                id=f"wall_{id_offset + len(walls_out):03d}",
                confidence=round(min(1.0, nseg / max(len(wall_pts) * 0.04, 1)), 3),
                classification="wall",
                source=ElementSource(method="normals"),
                axis=[[round(float(p0[0]), 1), round(float(p0[1]), 1)],
                      [round(float(p1[0]), 1), round(float(p1[1]), 1)]],
                height=round(float(z_extent), 1),
                thickness=round(float(thickness), 1),
                z_min=round(float(inlier_pts[:, 2].min()), 1),
            ))

    return walls_out

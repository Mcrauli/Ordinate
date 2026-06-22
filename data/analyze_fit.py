"""
Analysoi seinien akselivirhe, paksuusvirhe ja päätepisteiden virhe pistepilveä vasten.
Käyttö: python data/analyze_fit.py data/output/apt_v29/model.json data/raw/apt_raw_merged.ply
"""
from __future__ import annotations
import sys, json
import numpy as np
import open3d as o3d
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks


def analyze(json_path: str, ply_path: str) -> None:
    with open(json_path) as f:
        model = json.load(f)

    cloud = o3d.io.read_point_cloud(ply_path)
    pts = np.asarray(cloud.points)
    span = pts.max(axis=0) - pts.min(axis=0)
    if span.max() < 200:
        pts = pts * 1000.0

    for w in model["walls"]:
        ax = w["axis"]
        p0 = np.array(ax[0], dtype=float)
        p1 = np.array(ax[1], dtype=float)
        length = float(np.linalg.norm(p1 - p0))
        if length < 1:
            continue
        along = (p1 - p0) / length
        normal = np.array([-along[1], along[0]])
        axis_D = float(np.dot(normal, p0))
        T_model = w.get("thickness", 0.0)

        z_lo = w["z_min"] + 200.0
        z_hi = w["z_min"] + w["height"] - 200.0
        along_proj = (pts[:, :2] - p0) @ along
        dist = pts[:, :2] @ normal - axis_D

        mask = (
            (along_proj >= 100.0) & (along_proj <= length - 100.0)
            & (np.abs(dist) <= 650.0)
            & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
        )
        if mask.sum() < 40:
            print(f"{w['id']}: liian vähän pisteitä\n")
            continue

        d_vals = dist[mask]
        hist, edges = np.histogram(d_vals, bins=np.arange(-653.75, 656.25, 2.5))
        centers = 0.5 * (edges[:-1] + edges[1:])
        smooth = uniform_filter1d(hist.astype(float), size=3)
        pks, props = find_peaks(smooth, height=smooth.max() * 0.08, distance=20)

        # Huiput laskevassa järjestyksessä
        peaks_sorted = sorted(pks, key=lambda p: smooth[p], reverse=True)

        # Parhaat 2 pintaa (T-liitospisteeseen sopivat)
        best_pair = None
        best_score = 0.0
        for ii in range(len(peaks_sorted)):
            for jj in range(ii + 1, len(peaks_sorted)):
                da = float(centers[peaks_sorted[ii]])
                db = float(centers[peaks_sorted[jj]])
                if abs(da) > 600.0 or abs(db) > 600.0:
                    continue
                t_pair = abs(da - db)
                if not (50.0 <= t_pair <= 450.0):
                    continue
                t_weight = 1.0 / (1.0 + abs(t_pair - T_model) / 50.0)
                score = (smooth[peaks_sorted[ii]] + smooth[peaks_sorted[jj]]) * t_weight
                if score > best_score:
                    best_score = score
                    best_pair = (da, db)

        # Päätepiste-analyysi
        face_tol = 35.0
        half_t = T_model / 2.0
        face_mask = (
            ((np.abs(dist - half_t) < face_tol) | (np.abs(dist + half_t) < face_tol) | (np.abs(dist) < face_tol))
            & (pts[:, 2] >= w["z_min"] - 50.0) & (pts[:, 2] <= w["z_min"] + w["height"] + 50.0)
            & (along_proj >= -400.0) & (along_proj <= length + 400.0)
        )
        if face_mask.sum() >= 20:
            ap = along_proj[face_mask]
            lo = float(np.percentile(ap, 2))
            hi = float(np.percentile(ap, 98))
            p0_err = lo    # positiivinen = data alkaa lo mm seinän sisältä
            p1_err = hi - length  # positiivinen = data jatkuu hi-length mm yli pään
        else:
            p0_err = p1_err = float("nan")

        # Tulosta
        if best_pair:
            d1, d2 = best_pair
            t_actual = abs(d1 - d2)
            center_offset = (d1 + d2) / 2.0
            t_err = t_actual - T_model
            print(f"{w['id']}: T_malli={T_model:.0f}mm T_scan={t_actual:.0f}mm "
                  f"(err={t_err:+.0f}mm)  akseli={center_offset:+.1f}mm  "
                  f"p0_err={p0_err:+.0f}mm p1_err={p1_err:+.0f}mm")
            # Näytä top-4 huippua
            top = peaks_sorted[:6]
            peaks_str = "  peaks: " + "  ".join(
                f"D={centers[p]:+.0f}mm(n={int(smooth[p])})" for p in top
            )
            print(peaks_str)
        else:
            top = peaks_sorted[:4]
            peaks_str = "  peaks: " + "  ".join(
                f"D={centers[p]:+.0f}mm(n={int(smooth[p])})" for p in top
            )
            print(f"{w['id']}: T_malli={T_model:.0f}mm  EI PARIA  "
                  f"p0_err={p0_err:+.0f}mm p1_err={p1_err:+.0f}mm")
            print(peaks_str)
        print()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Käyttö: python analyze_fit.py <model.json> <pilvi.ply>")
        sys.exit(1)
    analyze(sys.argv[1], sys.argv[2])

"""KORKEUSMITTARI (seinän korkeus = katto_z - lattia_z, +-1.5mm tavoite).

Korkeus asetetaan globaalisti laattatasoista. Mitataan kuinka tarkasti mallin
lattia/katto/korkeus vastaa pilvestä sub-bin-piikkisovituksella mitattuja
lattia- ja kattotasoja (terävät tasot → fyysinen lattia sub-mm).

Cache data/_qa_zband.ply = lattia+katto-kaistat täydellä resalla (kerran).

Aja:  PYTHONPATH=src .venv/Scripts/python data/_height_qa.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import open3d as o3d
from _paths import DOWNLOADS, REPO  # portable dev-tool paths

ROOT = Path(str(REPO))
APT = Path(str(DOWNLOADS / "raw_scans_apartment/apartment"))
MODEL = ROOT / "data" / "output" / "_contour_ifc" / "floor_00" / "model.json"
ZBAND = ROOT / "data" / "_qa_zband.ply"


def _build_zband() -> None:
    from scan2bim.core.geometry.loader import load_point_cloud
    scans = sorted(APT.glob("scan_*.ply"))
    c0 = load_point_cloud(scans[0])
    z = np.asarray(c0.points)[:, 2]
    zmin, zmax = float(z.min()), float(z.max())
    fl, ce = zmin + 0.10 * (zmax - zmin), zmax - 0.10 * (zmax - zmin)
    merged = o3d.geometry.PointCloud()
    for p in scans:
        c = load_point_cloud(p)
        c.normals = o3d.utility.Vector3dVector()
        c.colors = o3d.utility.Vector3dVector()
        pts = np.asarray(c.points)
        m = (np.abs(pts[:, 2] - fl) < 120.0) | (np.abs(pts[:, 2] - ce) < 120.0)
        merged += c.select_by_index(np.where(m)[0])
        print(p.name, len(merged.points), flush=True)
    o3d.io.write_point_cloud(str(ZBAND), merged)
    print("ZBAND", len(merged.points), "->", ZBAND, flush=True)


def _subbin_peak(z: np.ndarray, region: str) -> float:
    """Dominantti taso = tihein z-piikki annetussa puoliskossa (suurin pinta-ala).

    Korkeus määritellään PÄÄtasojen (suurin lattia/katto) väliksi, ei ääripisteistä:
    ylhäällä/alhaalla on harvoja hajapisteitä jotka eivät ole rakenteita.
    """
    zmin, zmax = float(z.min()), float(z.max())
    mid = 0.5 * (zmin + zmax)
    near = z[z < mid] if region == "floor" else z[z > mid]
    if len(near) < 50:
        return zmin if region == "floor" else zmax
    bw = 2.0
    counts, edges = np.histogram(near, bins=max(int((near.max() - near.min()) / bw), 8))
    centers = 0.5 * (edges[:-1] + edges[1:])
    k = int(np.argmax(counts))  # tihein bini = dominantti taso
    if 0 < k < len(counts) - 1:
        c0, c1, c2 = (float(counts[k - 1]), float(counts[k]), float(counts[k + 1]))
        d = c0 - 2 * c1 + c2
        delta = max(-0.5, min(0.5, 0.5 * (c0 - c2) / d)) if abs(d) > 1e-9 else 0.0
        return float(centers[k] + delta * bw)
    return float(centers[k])


def main() -> None:
    if not ZBAND.exists():
        print("Rakennetaan z-kaista (kerran)...")
        _build_zband()

    pts = np.asarray(o3d.io.read_point_cloud(str(ZBAND)).points)
    z = pts[:, 2]
    zmin, zmax = float(z.min()), float(z.max())
    gt_floor = _subbin_peak(z, "floor")
    gt_ceil = _subbin_peak(z, "ceiling")
    gt_h = gt_ceil - gt_floor

    m = json.loads(MODEL.read_text())
    m_floor = min((w["z_min"] for w in m["walls"]), default=0.0)
    m_h = max((w["height"] for w in m["walls"]), default=0.0)
    m_ceil = m_floor + m_h

    print("KORKEUSMITTARI (malli vs pilvi-sub-bin)")
    print(f"  lattia : malli={m_floor:.1f}  pilvi={gt_floor:.1f}  poikkeama={abs(m_floor-gt_floor):.2f}mm")
    print(f"  katto  : malli={m_ceil:.1f}  pilvi={gt_ceil:.1f}  poikkeama={abs(m_ceil-gt_ceil):.2f}mm")
    print(f"  KORKEUS: malli={m_h:.1f}  pilvi={gt_h:.1f}  VIRHE={abs(m_h-gt_h):.2f}mm  "
          f"({'OK <1.5mm' if abs(m_h-gt_h) < 1.5 else 'yli 1.5mm'})")


if __name__ == "__main__":
    main()

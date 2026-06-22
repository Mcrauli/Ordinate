"""
Poikkeama-analyysi: pistepilvi vs. IFC-malli.

Lataa kunkin kerroksen raakapilven (sama Z-siivu kuin putki) ja mittaa jokaisen
pisteen etaisyyden IFC:n seina- ja laattapintoihin (Open3D RaycastingScene).
Raportoi 2.5 mm toleranssin osumat + keski-/RMS-/p95-/max-poikkeaman.

Kaytto:
    .venv\\Scripts\\python data\\deviation_check.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import open3d as o3d

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

RAW_DIR = ROOT / "data" / "raw" / "test_multiscan"
OUT_DIR = ROOT / "data" / "output" / "test_multiscan"

TOL = 2.5          # mm — vaadittu toleranssi
ASSOC_BAND = 50.0  # mm — talta etaisyydelta piste katsotaan kuuluvaksi mallinnetulle pinnalle
VOXEL = 1.0        # mm — kevyt downsample (sailyttaa alle-mm tarkkuuden)


def ifc_to_mesh(ifc_path: Path) -> o3d.geometry.TriangleMesh:
    """IFC-seinat + laatat -> yksi kolmioverkko maailmankoordinaateissa."""
    import ifcopenshell
    import ifcopenshell.geom

    f = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    # Maailmankoordinaatit + aukkojen vahennys paalle (oletus)
    try:
        settings.set(settings.USE_WORLD_COORDS, True)
        settings.set(settings.CONVERT_BACK_UNITS, True)  # palauta mm (muuten metreina)
    except Exception:
        settings.set("use-world-coords", True)
        settings.set("convert-back-units", True)

    all_v: list[np.ndarray] = []
    all_t: list[np.ndarray] = []
    offset = 0
    for cls in ("IfcWall", "IfcSlab"):
        for el in f.by_type(cls):
            if not el.Representation:
                continue
            shape = ifcopenshell.geom.create_shape(settings, el)
            v = np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
            t = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
            all_v.append(v)
            all_t.append(t + offset)
            offset += len(v)

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.concatenate(all_v))
    mesh.triangles = o3d.utility.Vector3iVector(np.concatenate(all_t))
    return mesh


def point_distances(cloud: o3d.geometry.PointCloud, mesh: o3d.geometry.TriangleMesh) -> np.ndarray:
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    pts = np.asarray(cloud.points, dtype=np.float32)
    d = scene.compute_distance(o3d.core.Tensor(pts, dtype=o3d.core.Dtype.Float32))
    return d.numpy()


def report(name: str, dist: np.ndarray) -> None:
    total = len(dist)
    assoc = dist[dist <= ASSOC_BAND]            # mallinnetuille pinnoille kuuluvat
    n_assoc = len(assoc)
    within = int((assoc <= TOL).sum())
    rms = float(np.sqrt(np.mean(assoc ** 2))) if n_assoc else 0.0
    print(f"\n=== {name} ===")
    print(f"  Pisteita yhteensa      : {total:,}")
    print(f"  Pinnoille kuuluvia      : {n_assoc:,}  ({100*n_assoc/total:.1f} %)   (<= {ASSOC_BAND:.0f} mm)")
    print(f"  --- poikkeama pinnasta (kuuluvat pisteet) ---")
    print(f"  <= {TOL} mm              : {within:,}  ({100*within/n_assoc:.1f} %)")
    print(f"  keskiarvo               : {assoc.mean():.2f} mm")
    print(f"  mediaani                : {np.median(assoc):.2f} mm")
    print(f"  RMS                     : {rms:.2f} mm")
    print(f"  p95                     : {np.percentile(assoc, 95):.2f} mm")
    print(f"  max                     : {assoc.max():.2f} mm")
    return assoc


def main() -> None:
    from scan2bim.core.geometry.floor_splitter import detect_floors_from_files
    from scan2bim.core.geometry.streaming import load_floor_slice

    paths = sorted(RAW_DIR.glob("scan_*.ply"))
    if not paths:
        print(f"Ei skannaustiedostoja: {RAW_DIR}  (aja ensin test_multiscan_ifc.py)")
        return

    floors = detect_floors_from_files(paths, sample_step=1)
    print(f"Kerroksia: {len(floors)}   toleranssi: {TOL} mm")

    all_assoc: list[np.ndarray] = []
    for i, (z_lo, z_hi) in enumerate(floors):
        ifc = OUT_DIR / f"floor_{i:02d}" / "model.ifc"
        if not ifc.exists():
            print(f"  IFC puuttuu: {ifc}")
            continue
        cloud = load_floor_slice(paths, z_lo, z_hi, voxel_size=VOXEL)
        mesh = ifc_to_mesh(ifc)
        dist = point_distances(cloud, mesh)
        a = report(f"Kerros {i}", dist)
        all_assoc.append(a)

    if all_assoc:
        merged = np.concatenate(all_assoc)
        within = int((merged <= TOL).sum())
        print(f"\n=== YHTEENSA ===")
        print(f"  Pinnoille kuuluvia      : {len(merged):,}")
        print(f"  <= {TOL} mm              : {within:,}  ({100*within/len(merged):.1f} %)")
        print(f"  keskiarvo / RMS         : {merged.mean():.2f} / {np.sqrt(np.mean(merged**2)):.2f} mm")


if __name__ == "__main__":
    main()

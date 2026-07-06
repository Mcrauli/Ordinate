"""Pistepilvi-loaderi: E57 / LAS/LAZ / PTS / PLY → open3d.PointCloud."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d

log = logging.getLogger(__name__)


def _autoscale(cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """Jos pilvi on metreissä (max laajuus < 200), skaalaa → mm."""
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return cloud
    span = pts.max(axis=0) - pts.min(axis=0)
    if span.max() < 200.0:
        cloud.points = o3d.utility.Vector3dVector(pts * 1000.0)
    return cloud


def load_and_merge(paths: list[Path]) -> o3d.geometry.PointCloud:
    """Lataa useita pistepilviä ja yhdistää ne yhdeksi."""
    merged = o3d.geometry.PointCloud()
    for p in paths:
        merged += load_point_cloud(p)
    return merged


def load_point_cloud(path: Path) -> o3d.geometry.PointCloud:
    """Lataa pistepilvi tiedostosta formaatista riippumatta."""
    suffix = path.suffix.lower()

    if suffix == ".e57":
        return _autoscale(_load_e57(path))
    if suffix in {".las", ".laz"}:
        return _autoscale(_load_las(path))
    if suffix in {".pts", ".xyz"}:
        return _autoscale(_load_pts_xyz(path))
    if suffix in {".ply", ".pcd"}:
        cloud = o3d.io.read_point_cloud(str(path))
        if suffix == ".ply":
            cloud = _fix_truncated_ply(path, cloud)
        return _autoscale(cloud)

    raise ValueError(f"Tuntematon formaatti: {suffix}")


_PLY_TYPE_BYTES = {b"float": 4, b"float32": 4, b"double": 8, b"float64": 8,
                   b"uchar": 1, b"char": 1, b"uint8": 1, b"int8": 1,
                   b"ushort": 2, b"short": 2, b"uint16": 2, b"int16": 2,
                   b"uint": 4, b"int": 4, b"uint32": 4, b"int32": 4}


def _ply_binary_layout(path: Path) -> tuple[int, int, int] | None:
    """(payload_alku, vertex_count, vertex_stride_bytes) binääri-PLY:lle,
    None jos ascii/lista-propertyja/parsinta ei onnistu."""
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return None
    if not head.startswith(b"ply"):
        return None
    offset = 0
    count = None
    stride = 0
    in_vertex = False
    binary = False
    for line in head.split(b"\n"):
        offset += len(line) + 1
        t = line.strip()
        if t.startswith(b"format"):
            binary = b"binary_little_endian" in t
        elif t.startswith(b"element"):
            parts = t.split()
            in_vertex = parts[1] == b"vertex"
            if in_vertex:
                count = int(parts[2])
        elif t.startswith(b"property") and in_vertex:
            parts = t.split()
            if parts[1] == b"list":
                return None
            b_ = _PLY_TYPE_BYTES.get(parts[1])
            if b_ is None:
                return None
            stride += b_
        elif t == b"end_header":
            if binary and count and stride:
                return offset, count, stride
            return None
    return None


def _fix_truncated_ply(path: Path, cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """Katkennut siirto/lataus tuottaa vajaan tiedoston. o3d EI kerro sitä:
    se varaa headerin lupaaman bufferin ja palauttaa loppupään ROSKANA.
    Lasketaan tavuista montako pistettä tiedostossa oikeasti on, leikataan
    roskahäntä pois ja varoitetaan selkokielellä."""
    layout = _ply_binary_layout(path)
    if layout is None:
        return cloud
    payload_start, declared, stride = layout
    try:
        fsize = path.stat().st_size
    except OSError:
        return cloud
    n_real = min(declared, max((fsize - payload_start) // stride, 0))
    if n_real >= declared:
        return cloud
    if n_real < 0.5 * declared or n_real < 1000:
        raise ValueError(
            f"{path.name}: tiedosto on vajaa — headerin mukaan {declared:,} pistettä, "
            f"tavujen mukaan vain {n_real:,}. Siirtyikö/latautuiko tiedosto kokonaan?"
        )
    log.warning(
        "%s: tiedosto on vajaa — %s / %s pistettä (katkennut siirto/lataus?). "
        "Malli tehdään luetusta osasta.",
        path.name, f"{n_real:,}", f"{declared:,}",
    )
    pts = np.asarray(cloud.points)
    if len(pts) > n_real:
        cloud = cloud.select_by_index(np.arange(n_real))
    return cloud


def _load_e57(path: Path) -> o3d.geometry.PointCloud:
    import pye57
    e57 = pye57.E57(str(path))
    merged = o3d.geometry.PointCloud()
    for i in range(e57.scan_count):
        try:
            data = e57.read_scan(i, transform=True, ignore_missing_fields=True)
        except Exception:
            data = e57.read_scan(i, ignore_missing_fields=True)
        xyz = np.column_stack([data["cartesianX"], data["cartesianY"], data["cartesianZ"]])
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
        merged += cloud
    return merged


def scanner_origins(path: Path) -> list[np.ndarray]:
    """E57:n skannerien origot (mm). Muut formaatit → tyhjä (ei pose-tietoa)."""
    if path.suffix.lower() != ".e57":
        return []
    try:
        import pye57
        e57 = pye57.E57(str(path))
    except Exception:
        return []
    origins: list[np.ndarray] = []
    for i in range(e57.scan_count):
        try:
            header = e57.get_header(i)
            t = np.asarray(header.translation, dtype=float)
            if np.linalg.norm(t) < 200.0:   # metreissä → mm
                t = t * 1000.0
            origins.append(t)
        except Exception:
            continue
    return origins


def _load_pts_xyz(path: Path) -> o3d.geometry.PointCloud:
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            try:
                rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                continue
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(rows, dtype=np.float64))
    return cloud


def _load_las(path: Path) -> o3d.geometry.PointCloud:
    import laspy
    las = laspy.read(str(path))
    xyz = np.column_stack([las.x, las.y, las.z])
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return cloud

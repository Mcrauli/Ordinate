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


def load_point_cloud(path: Path, e57_colors: bool = False) -> o3d.geometry.PointCloud:
    """Lataa pistepilvi tiedostosta formaatista riippumatta.

    e57_colors: lue E57:n RGB (opt-in). Oletus pois → putki/detektio ennallaan;
    katselin pyytää True (renderöinti värilliseksi). PLY/LAS lataavat värit aina."""
    suffix = path.suffix.lower()

    if suffix == ".e57":
        return _autoscale(_load_e57(path, with_colors=e57_colors))
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

_PLY_TYPE_NP = {b"float": "f4", b"float32": "f4", b"double": "f8", b"float64": "f8",
                b"uchar": "u1", b"char": "i1", b"uint8": "u1", b"int8": "i1",
                b"ushort": "u2", b"short": "i2", b"uint16": "u2", b"int16": "i2",
                b"uint": "u4", b"int": "i4", b"uint32": "u4", b"int32": "i4"}


def _ply_fields(path: Path) -> tuple[int, int, list, bool] | None:
    """(payload_alku, vertex_count, [(name, ply_type)…], little_endian) binääri-
    PLY:lle. None jos ascii/lista-propertyja/parsinta ei onnistu."""
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError:
        return None
    if not head.startswith(b"ply"):
        return None
    offset = 0
    count = None
    fields: list = []
    in_vertex = False
    binary = False
    little = True
    for line in head.split(b"\n"):
        offset += len(line) + 1
        t = line.strip()
        if t.startswith(b"format"):
            binary = b"binary_" in t
            little = b"binary_little_endian" in t
        elif t.startswith(b"element"):
            parts = t.split()
            in_vertex = parts[1] == b"vertex"
            if in_vertex:
                count = int(parts[2])
        elif t.startswith(b"property") and in_vertex:
            parts = t.split()
            if parts[1] == b"list" or parts[1] not in _PLY_TYPE_BYTES:
                return None
            fields.append((parts[2].decode("ascii", "replace"), parts[1]))
        elif t == b"end_header":
            if binary and count and fields:
                return offset, count, fields, little
            return None
    return None


def _ply_binary_layout(path: Path) -> tuple[int, int, int] | None:
    """(payload_alku, vertex_count, vertex_stride_bytes) binääri-PLY:lle,
    None jos ascii/lista-propertyja/parsinta ei onnistu."""
    parsed = _ply_fields(path)
    if parsed is None:
        return None
    offset, count, fields, _ = parsed
    stride = sum(_PLY_TYPE_BYTES[t] for _, t in fields)
    return offset, count, stride


def _ply_dtype(path: Path):
    """(payload_alku, n_real, numpy-structured-dtype) binääri-PLY:lle, None jos
    ei tue. n_real = tavuista laskettu todellinen pistemäärä (leikkaa roskahännän)."""
    parsed = _ply_fields(path)
    if parsed is None:
        return None
    offset, declared, fields, little = parsed
    order = "<" if little else ">"
    dt = np.dtype([(name, order + _PLY_TYPE_NP[t].encode().decode())
                   for name, t in fields])
    names = {n.lower() for n, _ in fields}
    if not {"x", "y", "z"} <= names:
        return None
    try:
        fsize = path.stat().st_size
    except OSError:
        return None
    n_real = min(declared, max((fsize - offset) // dt.itemsize, 0))
    return offset, n_real, dt


def _iter_ply_chunks(f, offset, n_real, dt, chunk):
    """Tuottaa PLY:n vertex-lohkot (numpy structured) yksi kerrallaan."""
    f.seek(offset)
    remaining = n_real
    while remaining > 0:
        buf = np.fromfile(f, dtype=dt, count=min(chunk, remaining))
        if len(buf) == 0:
            break
        remaining -= len(buf)
        yield buf


def read_ply_xyz_band(
    path: Path, z_lo: float, z_hi: float, chunk: int = 4_000_000,
    max_points: int = 0,
) -> np.ndarray | None:
    """Lukee binääri-PLY:n LOHKOISSA ja pitää vain Z-kaistan [z_lo, z_hi] pisteet.
    Huippumuisti = yksi lohko + valmis taulukko (ei vstack-tuplausta) — iso skanni
    ei kaada muistia. Palauttaa Nx3 float64 (tiedoston omassa koordinaatistossa,
    skaalaamaton). None jos ei tuettu binääri-PLY → kutsuja fallbackaa o3d:hen.

    max_points>0: jos kaistassa on enemmän, OHENNETAAN satunnaisesti tähän määrään.
    Satunnaisohennus säilyttää piikin PAIKAN (toisin kuin voxelointi, joka siirtää
    sitä sentroidi-biaksella) → paksuusmittauksen ali-mm-tarkkuus säilyy, muisti
    pysyy rajattuna mille tahansa skannikoolle."""
    parsed = _ply_dtype(path)
    if parsed is None:
        return None
    offset, n_real, dt = parsed
    nm = {n.lower(): n for n in dt.names}
    xn, yn, zn = nm["x"], nm["y"], nm["z"]

    # Passi 1: laske kaistan pisteet (vain z luetaan) → tarkka esivaraus, ei tuplausta.
    total = 0
    with open(path, "rb") as f:
        for buf in _iter_ply_chunks(f, offset, n_real, dt, chunk):
            z = buf[zn]
            total += int(((z >= z_lo) & (z <= z_hi)).sum())
    if total == 0:
        return np.zeros((0, 3), dtype=np.float64)

    keep = total if max_points <= 0 else min(total, max_points)
    prob = keep / total
    rng = np.random.default_rng(0)
    out = np.empty((keep, 3), dtype=np.float64)

    # Passi 2: täytä esivarattu taulukko (satunnaisohennus jos keep < total).
    filled = 0
    with open(path, "rb") as f:
        for buf in _iter_ply_chunks(f, offset, n_real, dt, chunk):
            if filled >= keep:
                break
            z = buf[zn].astype(np.float64)
            m = (z >= z_lo) & (z <= z_hi)
            if not m.any():
                continue
            xs, ys, zs = buf[xn][m].astype(np.float64), buf[yn][m].astype(np.float64), z[m]
            if prob < 1.0:
                sel = rng.random(len(zs)) < prob
                xs, ys, zs = xs[sel], ys[sel], zs[sel]
            take = min(len(zs), keep - filled)
            out[filled:filled + take, 0] = xs[:take]
            out[filled:filled + take, 1] = ys[:take]
            out[filled:filled + take, 2] = zs[:take]
            filled += take
    return out[:filled]


def ply_band_chunks(path: Path, z_lo: float, z_hi: float, chunk: int = 4_000_000):
    """Generaattori: tuottaa binääri-PLY:n Z-kaistan [z_lo, z_hi] pisteet Nx3
    float64 -lohkoina (tiedoston omassa koordinaatistossa, skaalaamaton). Kutsuja
    voxeloi/kasaa lohkot heti → koko kaistaa ei koskaan pidetä muistissa
    kerralla. Palauttaa None jos ei tuettu binääri-PLY."""
    parsed = _ply_dtype(path)
    if parsed is None:
        return None
    offset, n_real, dt = parsed
    nm = {n.lower(): n for n in dt.names}
    xn, yn, zn = nm["x"], nm["y"], nm["z"]

    def _gen():
        with open(path, "rb") as f:
            for buf in _iter_ply_chunks(f, offset, n_real, dt, chunk):
                z = buf[zn].astype(np.float64)
                m = (z >= z_lo) & (z <= z_hi)
                if not m.any():
                    continue
                yield np.column_stack(
                    [buf[xn][m].astype(np.float64),
                     buf[yn][m].astype(np.float64), z[m]])
    return _gen()


def ply_autoscale_factor(path: Path) -> float:
    """Metri→mm-kerroin (_autoscale sama sääntö) ilman koko tiedoston latausta:
    lukee vain ensimmäisen lohkon ja katsoo laajuuden. Rakennuksen osittainenkin
    laajuus ylittää 200 mm reippaasti → metri-vs-mm-päätös on turvallinen otoksesta."""
    parsed = _ply_dtype(path)
    if parsed is None:
        return 1.0
    offset, n_real, dt = parsed
    nm = {n.lower(): n for n in dt.names}
    with open(path, "rb") as f:
        f.seek(offset)
        buf = np.fromfile(f, dtype=dt, count=min(4_000_000, n_real))
    if len(buf) == 0:
        return 1.0
    xyz = np.column_stack([buf[nm["x"]], buf[nm["y"]], buf[nm["z"]]]).astype(np.float64)
    span = xyz.max(axis=0) - xyz.min(axis=0)
    return 1000.0 if span.max() < 200.0 else 1.0


def read_ply_z(
    path: Path, max_keep: int = 8_000_000, chunk: int = 4_000_000
) -> np.ndarray | None:
    """Vain Z-koordinaatit binääri-PLY:stä lohkoluvulla, desimoituna enintään
    max_keep pisteeseen. Kerrostunnistuksen histogrammille riittää otos — ei koko
    tiedostoa muistiin. None jos ei tuettu binääri-PLY."""
    parsed = _ply_dtype(path)
    if parsed is None:
        return None
    offset, n_real, dt = parsed
    zn = {n.lower(): n for n in dt.names}["z"]
    step = max(1, n_real // max_keep)
    out: list[np.ndarray] = []
    with open(path, "rb") as f:
        f.seek(offset)
        remaining = n_real
        while remaining > 0:
            n = min(chunk, remaining)
            buf = np.fromfile(f, dtype=dt, count=n)
            if len(buf) == 0:
                break
            out.append(buf[zn][::step].astype(np.float32))
            remaining -= len(buf)
    if not out:
        return np.zeros((0,), dtype=np.float32)
    return np.concatenate(out)


def ply_z_range(path: Path, chunk: int = 4_000_000) -> tuple[float, float] | None:
    """Z-min/max binääri-PLY:stä lohkoluvulla — ei lataa koko tiedostoa muistiin.
    None jos ei tuettu binääri-PLY."""
    parsed = _ply_dtype(path)
    if parsed is None:
        return None
    offset, n_real, dt = parsed
    zn = {n.lower(): n for n in dt.names}["z"]
    zmn, zmx = np.inf, -np.inf
    with open(path, "rb") as f:
        f.seek(offset)
        remaining = n_real
        while remaining > 0:
            n = min(chunk, remaining)
            buf = np.fromfile(f, dtype=dt, count=n)
            if len(buf) == 0:
                break
            z = buf[zn].astype(np.float64)
            zmn = min(zmn, float(z.min()))
            zmx = max(zmx, float(z.max()))
            remaining -= len(buf)
    if not np.isfinite(zmn):
        return None
    return zmn, zmx


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


def _load_e57(path: Path, with_colors: bool = False) -> o3d.geometry.PointCloud:
    # with_colors on OPT-IN (oletus pois): värit muuttaisivat väritietoisen
    # semanttisen suodattimen tulosta E57:llä (mitattu: lobby pilarit 14→10),
    # eikä sitä voi ilman GT:tä validoida. Putki EI pyydä värejä → detektio
    # ennallaan; VAIN katselin pyytää (harmaan "mössön" korjaus renderöintiin).
    import pye57
    try:
        e57 = pye57.E57(str(path))
        n_scans = e57.scan_count
    except Exception as exc:  # noqa: BLE001 — avaus epäonnistui = vaurio/vajaa
        raise ValueError(
            f"{path.name}: E57-tiedostoa ei voitu avata — mahdollisesti vajaa tai "
            f"vaurioitunut siirrossa/latauksessa ({type(exc).__name__})."
        ) from exc
    merged = o3d.geometry.PointCloud()
    failed = 0
    for i in range(n_scans):
        try:
            try:
                data = e57.read_scan(i, colors=with_colors, transform=True, ignore_missing_fields=True)
            except Exception:  # noqa: BLE001 — pose-muunnos epäonnistui, koeta ilman
                data = e57.read_scan(i, colors=with_colors, ignore_missing_fields=True)
        except Exception:  # noqa: BLE001 — koko skanni lukukelvoton (katkennut siirto?)
            failed += 1
            continue
        xyz = np.column_stack([data["cartesianX"], data["cartesianY"], data["cartesianZ"]])
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
        if with_colors and all(k in data for k in ("colorRed", "colorGreen", "colorBlue")):
            rgb = np.column_stack([data["colorRed"], data["colorGreen"], data["colorBlue"]]).astype(np.float64)
            mx = float(rgb.max()) if rgb.size else 0.0
            if mx > 1.0:
                rgb /= 65535.0 if mx > 255.0 else 255.0
            cloud.colors = o3d.utility.Vector3dVector(np.clip(rgb, 0.0, 1.0))
        merged += cloud
    if len(merged.points) == 0:
        raise ValueError(
            f"{path.name}: E57:stä ei saatu yhtään pistettä ({n_scans} skannia, "
            f"{failed} lukukelvotonta) — tyhjä tai vaurioitunut tiedosto."
        )
    if failed:
        log.warning(
            "%s: %d / %d skannia ei voitu lukea (katkennut siirto/lataus?). "
            "Malli tehdään luetuista skanneista.", path.name, failed, n_scans,
        )
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
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows = []
    skipped = 0
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            try:
                rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                skipped += 1
    if not rows:
        raise ValueError(
            f"{path.name}: tiedostosta ei löytynyt yhtään pistettä — tyhjä tai "
            f"vaurioitunut tiedosto."
        )
    # Yksittäinen katkennut viimeinen rivi on normaalia; suuri osuus lukukelvottomia
    # rivejä viittaa vaurioon/keskeytyneeseen siirtoon → varoita selkokielellä.
    total = len(rows) + skipped
    if skipped > max(1, int(0.1 * total)):
        log.warning(
            "%s: %s / %s riviä oli lukukelvottomia (vaurioitunut tai keskeytynyt "
            "tiedosto?). Malli tehdään luetuista.", path.name, f"{skipped:,}", f"{total:,}",
        )
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.array(rows, dtype=np.float64))
    return cloud


def _load_las(path: Path) -> o3d.geometry.PointCloud:
    import laspy
    try:
        las = laspy.read(str(path))
    except Exception as exc:  # noqa: BLE001 — laspy nostaa vajaasta/vaurioituneesta
        raise ValueError(
            f"{path.name}: LAS/LAZ-tiedostoa ei voitu lukea — mahdollisesti vajaa tai "
            f"vaurioitunut siirrossa/latauksessa ({type(exc).__name__})."
        ) from exc
    declared = int(getattr(las.header, "point_count", 0) or 0)
    xyz = np.column_stack([las.x, las.y, las.z])
    n = len(xyz)
    if n == 0:
        raise ValueError(
            f"{path.name}: LAS/LAZ-tiedostossa ei ole pisteitä — tyhjä tai vaurioitunut."
        )
    # Header lupaa point_count pistettä; jos luettu selvästi vähemmän, siirto katkesi.
    if declared and n < declared:
        if n < 0.5 * declared or n < 1000:
            raise ValueError(
                f"{path.name}: tiedosto on vajaa — headerin mukaan {declared:,} pistettä, "
                f"luettu vain {n:,}. Siirtyikö/latautuiko tiedosto kokonaan?"
            )
        log.warning(
            "%s: tiedosto on vajaa — %s / %s pistettä (katkennut siirto/lataus?). "
            "Malli tehdään luetusta osasta.", path.name, f"{n:,}", f"{declared:,}",
        )
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    return cloud

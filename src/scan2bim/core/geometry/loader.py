"""Pistepilvi-loaderi: E57 / LAS/LAZ / PTS / PLY → open3d.PointCloud."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import open3d as o3d

log = logging.getLogger(__name__)


_SPAN_MM = 200.0        # tätä pienempi laajuus ei ole rakennus millimetreinä
_SPACING_M = 0.5        # metripilven pisteväli; mitattu mm-pilvistä ≥ 2


def metre_scale(xyz: np.ndarray) -> float:
    """1000.0 jos pilvi on metreissä, muuten 1.0.

    Pelkkä laajuus sitoisi säännön rakennuksen KOKOON: 250 m halli metreissä
    jää skaalaamatta ja koko putki näkee 250 mm rakennuksen — ilman virhettä.
    Pisteväli on koosta riippumaton: mitattu Rohbau (metrit) 0.016–0.024,
    mm-pilvet (retail, apartment) 2–124.
    """
    if len(xyz) == 0:
        return 1.0
    if float((xyz.max(axis=0) - xyz.min(axis=0)).max()) < _SPAN_MM:
        return 1000.0
    sp = _nn_spacing(np.asarray(xyz, dtype=np.float64))
    return 1000.0 if sp == sp and sp < _SPACING_M else 1.0


def _nn_spacing(xyz: np.ndarray) -> float:
    """Mediaanietäisyys lähimpään naapuriin; nan jos ei mitattavissa.

    Nollaetäisyydet karsitaan: kaksoiskappaleet vetäisivät mediaanin nollaan ja
    väittäisivät jokaista pilveä metreiksi.
    """
    from scipy.spatial import cKDTree

    if len(xyz) < 100:
        return float("nan")
    n = min(len(xyz), 20_000)
    idx = np.linspace(0, len(xyz) - 1, n).astype(np.int64)
    # balanced_tree/compact_nodes ovat RAKENNUSAJAN optimointeja: kysely on
    # tarkka kummallakin ja `d[:, 1]` on etäisyys, ei indeksi, joten arvo on
    # sama. 24 M pisteen puu rakentuu näin murto-osassa ajasta.
    tree = cKDTree(xyz, balanced_tree=False, compact_nodes=False)
    d, _ = tree.query(xyz[idx], k=2)
    d = d[:, 1]
    d = d[d > 0.0]
    return float(np.median(d)) if len(d) else float("nan")


def _autoscale(cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
    """Jos pilvi on metreissä, skaalaa → mm."""
    pts = np.asarray(cloud.points)
    if len(pts) and metre_scale(pts) != 1.0:
        cloud.points = o3d.utility.Vector3dVector(pts * 1000.0)
    return cloud


_MERGE_VOXEL_MM = 10.0        # mm — esiharvennus monen skannin yhdistämisessä
_MERGE_RAW_LIMIT = 60_000_000  # pistettä: tätä isompi yhdistelmä ei mahdu raakana


def load_and_merge(paths: list[Path], voxel: float | None = None) -> o3d.geometry.PointCloud:
    """Lataa useita pistepilviä ja yhdistää ne yhdeksi.

    Jokainen pilvi harvennetaan ENNEN yhdistämistä, koska muuten koko
    keilausprojekti on hetken raakana muistissa: koulun kellari on 37 asemaa
    ja miljardi pistettä eli ~24 GB pelkkää geometriaa, vaikka työpilvi on
    lopulta 25 M pistettä. Käyttöliittymä sallii kaikkien asemien valinnan,
    joten ilman tätä se lupaa jotain mitä kone ei kestä.

    Harvennus on tässä kohdassa ilmaista: esikäsittely voxeloi saman pilven
    joka tapauksessa, ja `_MERGE_VOXEL_MM` on selvästi tiheämpi kuin
    detektiovoxel (auto-voxel 25 mm), joten mitattava geometria ei muutu.
    Yhden tiedoston polku EI harvenna — silloin muistiongelmaa ei ole eikä
    tulos saa muuttua bittiäkään.
    """
    if len(paths) == 1:
        return load_point_cloud(paths[0])

    step = _MERGE_VOXEL_MM if voxel is None else max(float(voxel), 1.0)
    merged = o3d.geometry.PointCloud()
    for p in paths:
        cloud = load_point_cloud(p)
        if len(cloud.points) and step > 0.0:
            cloud = cloud.voxel_down_sample(step)
        merged += cloud
        if len(merged.points) > _MERGE_RAW_LIMIT:
            merged = merged.voxel_down_sample(step)
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
    lukee vain ensimmäisen lohkon. Lohko on yhtenäinen, joten myös pisteväli on
    siitä mitattavissa → metri-vs-mm-päätös on turvallinen otoksesta."""
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
    return metre_scale(xyz)


_E57_CHUNK = 4_000_000


def _e57_scan_chunks(e57, index: int, chunk: int):
    """Yhden skannin pisteet LOHKOISSA (N,3) — pose sovellettuna, invalidit pois.

    `read_scan` varaa koko skannin kerralla; iso keilaus on yksi 1 mrd pisteen
    skanni, jolloin sitä ei voi ladata lainkaan. Sama libE57-lukija palvelee
    lohkoittain: `reader.read()` täyttää puskurin ja palauttaa määrän.
    Palauttaa heti None-tyhjänä jos skanni ei ole karteesinen (kutsuja
    palautuu koko skannin lukuun, jota EI muuteta).
    """
    header = e57.get_header(index)
    xyz_fields = ["cartesianX", "cartesianY", "cartesianZ"]
    if not all(f in header.point_fields for f in xyz_fields):
        return
    valid = "cartesianInvalidState"
    fields = xyz_fields + ([valid] if valid in header.point_fields else [])
    data, buffers = e57.make_buffers(fields, chunk)
    reader = header.points.reader(buffers)
    pose = header.has_pose()
    try:
        while True:
            got = reader.read()
            if got == 0:
                break
            xyz = np.column_stack([data[f][:got] for f in xyz_fields])
            if valid in data:
                xyz = xyz[~data[valid][:got].astype("?")]
            if pose and len(xyz):
                xyz = e57.to_global(xyz, header.rotation, header.translation)
            yield xyz
    finally:
        reader.close()


_E57_BIG = 40_000_000   # sama raja kuin PLY:llä: tätä pienempi luetaan kerralla


def _e57_is_chunkable(path: Path, n_paths: int = 1) -> bool:
    """Onko tämä e57 sekä LOHKOTTAVISSA että niin iso että se pitää lohkoa.

    Lohkoluku EI ole tulokseltaan neutraali: voxelointi tapahtuu lohkorajoilla
    ja kerroshistogrammi luetaan desimoituna, joten kerrosraja voi siirtyä
    senttejä (mitattu gargage.e57: kaista 2.60 → 2.57 m, malli 11 → 9 seinää).
    Siksi sitä käytetään VAIN kun koko tiedosto ei muuten mahtuisi muistiin —
    täsmälleen sama sääntö kuin `_big_ply`:llä.

    ``n_paths``: raja on mitoitettu YHDELLE tiedostolle, mutta keilausprojekti
    on monta keskikokoista. Koulun kellari on 36 asemaa á 27 M pistettä eli
    alle 40 M rajan jokainen, mutta yhteensä miljardi — ja `load_floor_slice`
    kasaa ne samaan pilveen, joten ajo kaatui `bad allocation`-virheeseen
    paksuusmittauksen kohdalla. Kun tiedostoja on monta, raja jaetaan niiden
    määrällä: silloin lohkoluku kytkeytyy päälle juuri silloin kun summa ei
    mahtuisi muistiin."""
    try:
        import pye57
        e57 = pye57.E57(str(path))
        if not all(
            all(f in e57.get_header(i).point_fields
                for f in ("cartesianX", "cartesianY", "cartesianZ"))
            for i in range(e57.scan_count)
        ):
            return False
        limit = _E57_BIG if n_paths <= 1 else max(_E57_BIG // n_paths, 2_000_000)
        return sum(e57.get_header(i).point_count
                   for i in range(e57.scan_count)) >= limit
    except Exception:  # noqa: BLE001 — ei lohkottavissa = käytä koko skannin lukua
        return False


def e57_autoscale_factor(path: Path) -> float:
    """Metri→mm-kerroin (_autoscale sama sääntö) lukematta koko tiedostoa."""
    import pye57
    e57 = pye57.E57(str(path))
    for xyz in _e57_scan_chunks(e57, 0, min(_E57_CHUNK, 1_000_000)):
        if len(xyz) == 0:
            continue
        return metre_scale(xyz)
    return 1.0


def e57_xyz_chunks(path: Path, chunk: int = _E57_CHUNK):
    """Kaikki pisteet lohkoissa (N,3), MM-skaalattuna ja pose sovellettuna."""
    import pye57
    scale = e57_autoscale_factor(path)
    e57 = pye57.E57(str(path))
    for i in range(e57.scan_count):
        for xyz in _e57_scan_chunks(e57, i, chunk):
            if len(xyz) == 0:
                continue
            if scale != 1.0:
                xyz *= scale
            yield xyz


def e57_point_count(path: Path) -> int:
    import pye57
    e57 = pye57.E57(str(path))
    return sum(e57.get_header(i).point_count for i in range(e57.scan_count))


def e57_band_chunks(path: Path, z_lo: float, z_hi: float, chunk: int = _E57_CHUNK):
    """Z-kaistan pisteet lohkoissa (mm), kaikista skanneista. z-rajat MM:einä."""
    for xyz in e57_xyz_chunks(path, chunk):
        keep = (xyz[:, 2] >= z_lo) & (xyz[:, 2] <= z_hi)
        if keep.any():
            yield xyz[keep]


def read_e57_z(path: Path, max_keep: int = 8_000_000) -> np.ndarray | None:
    """Vain Z (mm) lohkoluvulla, desimoituna — kerrostunnistuksen histogrammille."""
    total = e57_point_count(path)
    step = max(1, total // max(max_keep, 1))
    out: list[np.ndarray] = []
    for xyz in e57_xyz_chunks(path):
        out.append(xyz[::step, 2].astype(np.float32))
    if not out:
        return np.zeros((0,), dtype=np.float32)
    return np.concatenate(out)


def e57_z_range(path: Path) -> tuple[float, float] | None:
    """Kaistarajojen laskentaan: min/max Z (mm) ilman koko tiedostoa muistiin."""
    lo, hi = np.inf, -np.inf
    for xyz in e57_xyz_chunks(path):
        z = xyz[:, 2]
        lo = min(lo, float(z.min()))
        hi = max(hi, float(z.max()))
    if not np.isfinite(lo):
        return None
    return lo, hi


def read_e57_xyz_band(
    path: Path, z_lo: float, z_hi: float, max_points: int = 0
) -> np.ndarray | None:
    """Kaista täysresana, satunnaisohennus kattoon — KAKSI PASSIA kuten PLY:llä.

    Ensin lasketaan kaistan pisteet, sitten täytetään esivarattu taulukko. Näin
    huippumuisti on yksi lohko + valmis taulukko, eikä koko kaistaa pidetä
    listassa (32 GB skannin kaista ei mahtuisi)."""
    total = 0
    for xyz in e57_band_chunks(path, z_lo, z_hi):
        total += len(xyz)
    if total == 0:
        return np.zeros((0, 3), dtype=np.float64)

    keep = total if max_points <= 0 else min(total, max_points)
    prob = keep / total
    rng = np.random.default_rng(0)
    out = np.empty((keep, 3), dtype=np.float64)

    filled = 0
    for xyz in e57_band_chunks(path, z_lo, z_hi):
        if filled >= keep:
            break
        if prob < 1.0:
            xyz = xyz[rng.random(len(xyz)) < prob]
        take = min(len(xyz), keep - filled)
        out[filled:filled + take] = xyz[:take]
        filled += take
    return out[:filled]


def read_e57_xyz_bands(
    path: Path, bands: list[tuple[float, float]], max_points: int = 0
) -> list[np.ndarray]:
    """Useampi kaista SAMASTA purusta — bitilleen sama kuin `read_e57_xyz_band`
    kullekin kaistalle erikseen.

    Pipeline luki paksuuskaistan ja 5 mm -pilven peräkkäin, ja kumpikin purki
    jokaisen tiedoston kahdesti (laskenta + täyttö): neljä purkua, joista kaksi
    riittää. Samuus perustuu kolmeen asiaan: raakalohkot tulevat samassa
    järjestyksessä, kaistan ehto on sama (`>=` ja `<=`), ja jokaisella kaistalla
    on oma `default_rng(0)` joka kuluttaa tasan yhtä monta lukua kuin sen
    kaistaan osuu pisteitä — tyhjä lohko ei kuluta mitään, joten lohkojako ei
    vaikuta valintaan.
    """
    nb = len(bands)
    totals = [0] * nb
    for xyz in e57_xyz_chunks(path, _E57_CHUNK):
        z = xyz[:, 2]
        for k, (lo, hi) in enumerate(bands):
            totals[k] += int(((z >= lo) & (z <= hi)).sum())

    keeps = [t if max_points <= 0 else min(t, max_points) for t in totals]
    probs = [(kp / t) if t else 1.0 for kp, t in zip(keeps, totals)]
    rngs = [np.random.default_rng(0) for _ in range(nb)]
    outs = [np.empty((kp, 3), dtype=np.float64) for kp in keeps]
    filled = [0] * nb

    if any(keeps):
        for xyz in e57_xyz_chunks(path, _E57_CHUNK):
            if all(f >= kp for f, kp in zip(filled, keeps)):
                break
            z = xyz[:, 2]
            for k, (lo, hi) in enumerate(bands):
                if filled[k] >= keeps[k]:
                    continue
                m = (z >= lo) & (z <= hi)
                if not m.any():
                    continue
                sub = xyz[m]
                if probs[k] < 1.0:
                    sub = sub[rngs[k].random(len(sub)) < probs[k]]
                take = min(len(sub), keeps[k] - filled[k])
                outs[k][filled[k]:filled[k] + take] = sub[:take]
                filled[k] += take
    return [o[:f] if t else np.zeros((0, 3), dtype=np.float64)
            for o, f, t in zip(outs, filled, totals)]


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
    """E57:n skannerien origot (mm). Muut formaatit → tyhjä (ei pose-tietoa).

    Yksikkö luetaan skannin PISTEISTÄ samalla säännöllä kuin itse pilvi
    (`e57_autoscale_factor`), koska pose on määritelmän mukaan samassa
    yksikössä kuin skannin karteesiset koordinaatit. Aiempi ehto oli origon
    NORMI alle 200 — se mittaa rakennuksen SIJAINTIA, ei sen yksikköä.
    Paikallisessa ruudukossa se pettää: koulun kellarin asemat ovat noin
    (200 m, 541 m), normi 576, joten metrit jäivät skaalaamatta ja origot
    olivat 1000× pielessä. Mitattu 37 asemalla: kertoimella 1 osui mallin
    alueelle 0/37, kertoimella 1000 **37/37**. Sama juurisyy kuin
    `metre_scale`:ssa — yksikkösääntö ei saa nojata rakennuksen kokoon eikä
    sijaintiin."""
    if path.suffix.lower() != ".e57":
        return []
    try:
        import pye57
        e57 = pye57.E57(str(path))
    except Exception:
        return []
    try:
        scale = e57_autoscale_factor(path)
    except Exception:  # noqa: BLE001 — pisteitä ei luettavissa → älä arvaa
        scale = 1.0
    origins: list[np.ndarray] = []
    for i in range(e57.scan_count):
        try:
            header = e57.get_header(i)
            origins.append(np.asarray(header.translation, dtype=float) * scale)
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

"""Muistitehokas lataus useista tiedostoista: yksi kerrallaan, Z-kaista suodatetaan heti."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import open3d as o3d


def _voxel_first_np(arr: np.ndarray, vs: float) -> np.ndarray:
    """Kevyt voxel-downsample: pitää yhden pisteen per vs-ruutu (ensimmäinen).
    Muisti = O(sort(N)), ei o3d:n hash-mapia (~10 GB 70M pisteelle). Riittää
    detektion tiheysmaskille (12mm-ruutu rasteroidaan pikseleiksi joka
    tapauksessa) — sentroidibias ei koske detektiota, vain paksuutta (raakapilvi)."""
    q = np.floor(arr / vs).astype(np.int64)
    q -= q.min(axis=0)
    dim = q.max(axis=0) + 1
    if int(dim[0]) * int(dim[1]) * int(dim[2]) < (1 << 62):
        key = (q[:, 0] * dim[1] + q[:, 1]) * dim[2] + q[:, 2]
        _, idx = np.unique(key, return_index=True)
    else:
        _, idx = np.unique(q, axis=0, return_index=True)
    return arr[idx].copy()


def _load_ply_band(
    path, z_lo, z_hi, voxel_size, max_points, n_paths,
    read_ply_xyz_band, ply_band_chunks, ply_autoscale_factor,
) -> o3d.geometry.PointCloud | None:
    """Lataa binääri-PLY:n Z-kaistan MUISTIRAJATUSTI.

    voxel_size>0 (detektio/refine): luetaan lohkoittain ja voxeloidaan HETI —
    akkumulaattori pysyy voxeloidun pilven kokoisena, koko täysresa-kaistaa ei
    koskaan pidetä muistissa (159M kerroskaista = 3.7 GB raakana).
    voxel_size==0 (paksuusmittaus): täysresa + satunnaisohennus kattoon
    (read_ply_xyz_band max_points). Palauttaa None jos ei tuettu binääri-PLY."""
    scale = ply_autoscale_factor(path)
    # per-tiedosto kattoraja jaetaan tiedostojen kesken (monikeilaus)
    mp = 0 if max_points <= 0 else max(1, max_points // max(n_paths, 1))

    # Kattorajattu lataus (thick JA iso refine) = täysresa + satunnaisohennus.
    # EI voxelointia: iso 5mm-kaista (SLAM-kohina) on ~100M eikä kutistu, ja o3d-
    # voxel siitä jumittaa/thrashaa. Satunnaisohennus on halpa JA tarkempi
    # pintamediaanille (ei sentroidibiasta). voxel<=0 (thick) tulee myös tänne.
    if voxel_size <= 0.0 or mp > 0:
        raw = read_ply_xyz_band(path, z_lo / scale, z_hi / scale, max_points=mp)
        if raw is None:
            return None
        if scale != 1.0:
            raw *= scale   # in-place, ei kopiota
        c = o3d.geometry.PointCloud()
        c.points = o3d.utility.Vector3dVector(raw)
        return c

    gen = ply_band_chunks(path, z_lo / scale, z_hi / scale)
    if gen is None:
        return None
    return _accumulate_voxeled(gen, scale, voxel_size)


def _load_e57_band(
    path, z_lo, z_hi, voxel_size, max_points, n_paths,
    read_e57_xyz_band, e57_band_chunks,
) -> o3d.geometry.PointCloud:
    """Lataa E57:n Z-kaistan MUISTIRAJATUSTI — sama kaksi moodia kuin PLY:llä.

    e57_band_chunks palauttaa jo MM-skaalatut pisteet (pose sovellettuna), joten
    z-rajoja ei jaeta skaalalla eikä lohkoja skaalata uudelleen."""
    mp = 0 if max_points <= 0 else max(1, max_points // max(n_paths, 1))
    if voxel_size <= 0.0 or mp > 0:
        raw = read_e57_xyz_band(path, z_lo, z_hi, max_points=mp)
        c = o3d.geometry.PointCloud()
        c.points = o3d.utility.Vector3dVector(raw)
        return c
    return _accumulate_voxeled(e57_band_chunks(path, z_lo, z_hi), 1.0, voxel_size)


def _accumulate_voxeled(gen, scale: float, voxel_size: float) -> o3d.geometry.PointCloud:
    """Kasaa kaistalohkot voxeloiden — koko kaistaa ei pidetä muistissa."""

    def _voxel(arr: np.ndarray) -> np.ndarray:
        if len(arr) == 0:
            return arr
        # Iso taulukko: o3d:n voxel_down_sample rakentaa hash-mapin joka syö
        # ~10 GB 70M pisteelle. Käytä kevyttä numpy-ruutudedupia (yksi piste/solu)
        # → muisti ~sort(N). Pieni taulukko: o3d-sentroidi (validoitu tarkkuus).
        if len(arr) > 30_000_000:
            return _voxel_first_np(arr, voxel_size)
        c = o3d.geometry.PointCloud()
        c.points = o3d.utility.Vector3dVector(arr)
        # .copy(): irrota o3d-puskurista → väliaikainen pilvi vapautuu heti
        return np.asarray(c.voxel_down_sample(voxel_size).points).copy()

    # Puskuroi RAAKAlohkot ~24M asti, sitten tyhjennä: voxeloi puskuri + sulauta
    # kertyneeseen (dedup lohkorajat). Sulautus laukeaa kerran per 24M SYÖTETTÄ
    # (ei per lohko) → voxeloitavaksi päätyy vain acc + ~24M, ei koko kaista,
    # eikä työ ole O(n²).
    acc: np.ndarray | None = None
    buf: list[np.ndarray] = []
    n_buf = 0

    # Tänne päädytään vain detektiolle (voxel>0, ei kattorajaa). Dedup
    # voxeloimalla pitää akun aidossa 12mm-ruutukoossa tiheysmaskille.
    def _flush():
        nonlocal acc, buf, n_buf
        if not buf:
            return
        v = _voxel(np.concatenate(buf) if len(buf) > 1 else buf[0])
        buf, n_buf = [], 0
        acc = v if acc is None else _voxel(np.concatenate([acc, v]))

    for xyz in gen:
        if scale != 1.0:
            xyz *= scale
        buf.append(xyz)
        n_buf += len(xyz)
        if n_buf >= 24_000_000:
            _flush()
    _flush()

    if acc is None:
        return o3d.geometry.PointCloud()
    out = o3d.geometry.PointCloud()
    out.points = o3d.utility.Vector3dVector(acc)
    return out


def read_workers(n_files: int, want: int = 4) -> int:
    """Montako tiedostoa luetaan rinnakkain.

    Mitattu neljalla kellarin e57:lla (834-977 MB): 2 prosessia 1.53x,
    4 prosessia 2.24x, 6 ei enaa parane — levy rajoittaa. Tulos on bitilleen
    sama kuin perakkain luettuna.

    Muisti on oikea rajoite eika ytimet: yksi 0.8 GB e57 vie lukiessa
    moninkertaisesti oman kokonsa, joten rinnakkaisuus rajataan vapaan
    muistin mukaan.
    """
    if n_files < 2:
        return 1
    try:
        import psutil  # noqa: PLC0415
        free_gb = psutil.virtual_memory().available / 1e9
        want = max(1, min(want, int(free_gb // 6)))
    except Exception:
        want = min(want, 2)
    return max(1, min(want, n_files))


def _slice_one(args):
    """Yhden tiedoston Z-kaista taulukkona. Moduulitasolla, jotta
    prosessipooli voi poimia sen (Windows spawn)."""
    (path, z_lo, z_hi, voxel_size, max_points, n_paths, want_sample) = args
    path = Path(path)
    from scan2bim.core.geometry.loader import (
        load_point_cloud, read_ply_xyz_band, ply_band_chunks, ply_autoscale_factor,
        _ply_dtype, _e57_is_chunkable, e57_band_chunks, read_e57_xyz_band,
    )

    slice_cloud: o3d.geometry.PointCloud | None = None
    _suffix = path.suffix.lower()
    _big_ply = False
    if _suffix == ".ply":
        _dt = _ply_dtype(path)
        _big_ply = _dt is not None and _dt[1] >= 40_000_000
    _big_e57 = _suffix == ".e57" and _e57_is_chunkable(path, n_paths)
    warn = None
    if _big_ply or _big_e57:
        try:
            if _big_ply:
                slice_cloud = _load_ply_band(
                    path, z_lo, z_hi, voxel_size, max_points, n_paths,
                    read_ply_xyz_band, ply_band_chunks, ply_autoscale_factor,
                )
            else:
                slice_cloud = _load_e57_band(
                    path, z_lo, z_hi, voxel_size, max_points, n_paths,
                    read_e57_xyz_band, e57_band_chunks,
                )
        except Exception as e:  # noqa: BLE001
            warn = f"  VAROITUS: {path.name} kaistaluku epäonnistui — {e}"
            slice_cloud = None

    if slice_cloud is not None:
        if len(slice_cloud.points) < 50:
            return None, None, warn
        _already_voxeled = True
    else:
        _already_voxeled = False
        try:
            cloud = load_point_cloud(path)
        except Exception as e:  # noqa: BLE001
            return None, None, f"  VAROITUS: {path.name} ohitettiin — {e}"

        # Vapauta normaalit ja värit heti — tarvitaan vain XYZ. Säästää ~1.3 GB/tiedosto.
        cloud.normals = o3d.utility.Vector3dVector()
        cloud.colors = o3d.utility.Vector3dVector()

        pts = np.asarray(cloud.points)
        mask = (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
        n = int(mask.sum())
        if n < 50:
            del cloud
            return None, None, warn

        idx = np.where(mask)[0]
        slice_cloud = cloud.select_by_index(idx)
        del cloud  # vapauta muisti ennen downsamplausta

    if voxel_size > 0.0 and not _already_voxeled:
        slice_cloud = slice_cloud.voxel_down_sample(voxel_size)

    sample = None
    if want_sample:
        sample = np.asarray(slice_cloud.voxel_down_sample(100.0).points).copy()
    return np.asarray(slice_cloud.points).copy(), sample, warn


def load_floor_slice(
    paths: list[Path],
    z_lo: float,
    z_hi: float,
    voxel_size: float = 1.0,
    progress_cb=None,
    icp_refine: bool = False,
    sample_out: list | None = None,
    max_points: int = 0,
) -> o3d.geometry.PointCloud:
    """
    Lataa vain Z-kaistan [z_lo, z_hi] kaikista tiedostoista.
    Huippumuisti = yhden tiedoston koko (ei kaikkien summa).

    icp_refine=True: kukin siivu kohdistetaan kasvavaan referenssiin ICP:llä,
    jotta karkeasta E57-posesta tulevat kahdentumat poistuvat.

    sample_out: jos annettu, siihen lisätään (tiedostonimi, karkea 100mm-otos)
    per tiedosto — skannien keskinäisen yhteensopivuuden tarkistukseen.
    """
    n = len(paths)
    want_sample = sample_out is not None
    jobs = [(str(p), z_lo, z_hi, voxel_size, max_points, n, want_sample) for p in paths]

    # ICP kohdistaa jokaisen siivun kasvavaan referenssiin → järjestys on osa
    # laskentaa eikä sitä voi rinnakkaistaa.
    workers = 1 if icp_refine else read_workers(n)

    def _use(i: int, path: Path, res) -> None:
        pts, sample, warn = res
        if warn and progress_cb:
            progress_cb(warn)
        if pts is None or not len(pts):
            return
        slice_cloud = o3d.geometry.PointCloud()
        slice_cloud.points = o3d.utility.Vector3dVector(pts)
        nonlocal merged, ref
        if icp_refine:
            from scan2bim.core.geometry.registration import align_to_reference
            if ref is not None:
                slice_cloud = align_to_reference(slice_cloud, ref)
            merged += slice_cloud
            ref = merged.voxel_down_sample(max(voxel_size * 8.0, 20.0))
        else:
            merged += slice_cloud
        if sample_out is not None and sample is not None:
            sample_out.append((path.name, sample))

    merged = o3d.geometry.PointCloud()
    ref: o3d.geometry.PointCloud | None = None  # kevyt referenssi ICP:lle
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor  # noqa: PLC0415
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i, (path, res) in enumerate(zip(paths, ex.map(_slice_one, jobs))):
                if progress_cb:
                    progress_cb(f"  [{i+1}/{n}] {path.name}")
                _use(i, path, res)
    else:
        for i, (path, job) in enumerate(zip(paths, jobs)):
            if progress_cb:
                progress_cb(f"  [{i+1}/{n}] {path.name}")
            _use(i, path, _slice_one(job))

    return merged


def check_scan_consistency(samples: list, dist_thr: float = 120.0) -> list[str]:
    """Palauttaa tiedostot jotka eivät jaa pintoja muiden skannien kanssa.

    Saman tilan skannit limittyvät: ison osan pisteistä on löydettävä
    vastinpiste muista skanneista. Eri kohteen skanni samassa koordinaatistossa
    risteää satunnaisesti → mediaanietäisyys muihin on suuri → varoitus.
    Mitattu: saman talon skannit medNN 6–37 mm (100 mm otoksella), kymmenen
    ERI asunnon setti 143–2720 mm → 120 mm erottaa täydellä marginaalilla."""
    if len(samples) < 2:
        return []
    from scipy.spatial import cKDTree
    suspicious: list[str] = []
    for i, (name, pts) in enumerate(samples):
        if len(pts) < 50:
            continue
        others = np.vstack([p for j, (_, p) in enumerate(samples) if j != i and len(p)])
        if len(others) < 50:
            continue
        tree = cKDTree(others)
        d, _ = tree.query(pts, k=1)
        if float(np.median(d)) > dist_thr:
            suspicious.append(name)
    return suspicious

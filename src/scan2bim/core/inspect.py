"""Skannin esitarkastus: mitä tästä tiedostosta oikeasti tulee sisään.

Putki tekee tuntemattomasta skannista useita oletuksia (yksikkö, lattia- ja
kattotaso, kerrosjako, pistetiheys) ja jos jokin niistä menee pieleen, virhe
näkyy vasta lopputuloksessa väärän kokoisena mallina. Tämä lukee ne oletukset
suoraan ja kertoo ne ennen ajoa, varoituksineen.

Käyttö koodista: `inspect_scan(Path(...))` → dict. CLI: `scan2bim inspect`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

# Varoituskynnykset ovat fysikaalisia, eivät skanniin viritettyjä:
_MIN_SPAN_MM = 1500.0        # tätä pienempi rakennus ei ole rakennus
_TALL_SPAN_MM = 12000.0      # yli tämän: joko monikerros tai rekisteröintivirhe
_SPARSE_MM = 60.0            # mediaanipisteväli: tätä harvempi ei kanna 100 mm seinää
_DENSE_MM = 2.0


def inspect_scan(path: Path, sample: int = 2_000_000) -> dict:
    """Lukee skannin oletukset ilman koko putken ajamista."""
    from scan2bim.core.geometry.floor_splitter import detect_floors
    from scan2bim.core.segmentation.slab_detector import _find_z_levels

    pts, total, dense = _read_sampled(Path(path), sample)
    out: dict = {"file": str(path), "points": int(total), "warnings": []}
    if total > len(pts):
        out["sampled"] = int(len(pts))
    if len(pts) < 1000:
        out["warnings"].append("alle 1000 pistettä — ei mallinnettavissa")
        return out

    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = hi - lo
    out["bbox_m"] = [round(float(v) / 1000.0, 2) for v in span]

    # Tiheys mitataan YHTENÄISESTÄ lohkosta: harvennettu näyte antaisi liian
    # suuren pistevälin ja väärän "harva skanni" -varoituksen.
    out["spacing_mm"] = round(_median_spacing(dense if len(dense) > 5000 else pts), 1)

    z = pts[:, 2]
    levels = _find_z_levels(pts)
    floor = next((v for v, k in levels if k == "floor"), float(z.min()))
    ceiling = next((v for v, k in levels if k == "ceiling"), float(z.max()))
    out["floor_mm"] = round(float(floor), 1)
    out["ceiling_mm"] = round(float(ceiling), 1)
    out["room_height_mm"] = round(float(ceiling - floor), 1)
    out["floors"] = [[round(float(a), 1), round(float(b), 1)] for a, b in detect_floors(z)]

    if span.max() < _MIN_SPAN_MM:
        out["warnings"].append(
            f"laajuus vain {span.max():.0f} mm — tarkista mittakaava, putki olettaa millimetrit")
    if span[2] > _TALL_SPAN_MM:
        out["warnings"].append(
            f"z-laajuus {span[2] / 1000.0:.1f} m — monikerros tai rekisteröintivirhe; "
            f"tarkista kerrosjako alta")
    if out["spacing_mm"] > _SPARSE_MM:
        out["warnings"].append(
            f"mediaanipisteväli {out['spacing_mm']:.0f} mm — harva skanni, "
            f"ohuet seinät ja aukot voivat jäädä löytymättä")
    if out["spacing_mm"] < _DENSE_MM:
        out["warnings"].append(
            f"mediaanipisteväli {out['spacing_mm']:.1f} mm — erittäin tiheä, "
            f"varaa muistia tai kasvata voxelia")
    if out["room_height_mm"] < _MIN_SPAN_MM:
        out["warnings"].append(
            f"lattian ja katon väli {out['room_height_mm']:.0f} mm — tasoja ei eroteltu")
    if len(out["floors"]) > 1:
        out["warnings"].append(
            f"{len(out['floors'])} kerrosta — jokainen mallinnetaan erikseen")
    return out


def _read_sampled(path: Path, sample: int) -> tuple[np.ndarray, int, np.ndarray]:
    """Lue korkeintaan `sample` pistettä. E57 luetaan skanni kerrallaan harventaen.

    Esitarkastuksen on toimittava juuri silloin kun tiedosto on liian iso
    ajettavaksi — 32 GB E57 ei mahdu muistiin, mutta sen oletukset pitää nähdä
    ENNEN ajoa, ei sen jälkeen.
    """
    from scan2bim.core.geometry.loader import load_point_cloud, metre_scale

    if path.suffix.lower() == ".e57":
        try:
            import pye57

            e57 = pye57.E57(str(path))
            chunks: list[np.ndarray] = []
            dense: np.ndarray | None = None
            total = 0
            n_scans = max(e57.scan_count, 1)
            per = max(sample // n_scans, 10_000)
            for i in range(e57.scan_count):
                try:
                    d = e57.read_scan(i, transform=True, ignore_missing_fields=True)
                except Exception:  # noqa: BLE001
                    continue
                xyz = np.column_stack([d["cartesianX"], d["cartesianY"], d["cartesianZ"]])
                total += len(xyz)
                if dense is None:
                    dense = xyz[:200_000].astype(np.float64)
                step = max(len(xyz) // per, 1)
                chunks.append(xyz[::step].astype(np.float64))
            if chunks:
                q = np.vstack(chunks)
                # Sama yksikkösääntö kuin loaderilla — mitattuna, ei arvattuna.
                # Tiheys luetaan yhtenäisestä lohkosta, ei harvennetusta näytteestä.
                scale = metre_scale(dense if dense is not None else q)
                return q * scale, total, (dense * scale if dense is not None else q)
        except Exception:  # noqa: BLE001 — pudotaan tavalliseen lataukseen
            pass

    pts = np.asarray(load_point_cloud(path).points, dtype=np.float64)
    if len(pts) > sample:
        mid = len(pts) // 2
        dense = pts[mid:mid + 200_000]
        return pts[::max(len(pts) // sample, 1)], len(pts), dense
    return pts, len(pts), pts


def _median_spacing(q: np.ndarray, k: int = 8) -> float:
    """Mediaanietäisyys lähimpään naapuriin — skannin todellinen resoluutio."""
    from scipy.spatial import cKDTree

    n = min(len(q), 20_000)
    idx = np.linspace(0, len(q) - 1, n).astype(np.int64)
    tree = cKDTree(q)
    d, _ = tree.query(q[idx], k=2)
    return float(np.median(d[:, 1]))


def format_report(info: dict) -> str:
    """Ihmisluettava raportti `inspect_scan`in tuloksesta."""
    if "bbox_m" not in info:
        lines = [f"{info['file']}: {info['points']:,} pistettä"]
        return "\n".join(lines + [f"  VAROITUS: {w}" for w in info["warnings"]])
    b = info["bbox_m"]
    lines = [
        f"{info['file']}",
        f"  pisteitä        {info['points']:,}"
        + (f"  (luettu näyte {info['sampled']:,})" if "sampled" in info else ""),
        f"  laajuus         {b[0]:.1f} × {b[1]:.1f} × {b[2]:.1f} m",
        f"  pisteväli       {info['spacing_mm']:.1f} mm (mediaani lähimpään naapuriin)",
        f"  lattia / katto  {info['floor_mm']:.0f} / {info['ceiling_mm']:.0f} mm"
        f"  → vapaa korkeus {info['room_height_mm'] / 1000.0:.2f} m",
        f"  kerroksia       {len(info['floors'])}",
    ]
    for a, c in info["floors"]:
        lines.append(f"                  {a:.0f} … {c:.0f} mm")
    for w in info["warnings"]:
        lines.append(f"  VAROITUS: {w}")
    if not info["warnings"]:
        lines.append("  ei varoituksia")
    return "\n".join(lines)

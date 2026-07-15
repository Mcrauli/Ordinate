"""Pistepilvi vs. IFC-malli -poikkeama (LOA) + matalan luottamuksen elementtien flägäys.

Mittaa jokaisen pisteen etäisyyden mallin pintoihin (Open3D RaycastingScene) ja
raportoi toleranssin osumat seinille ja laatoille erikseen. USIBD LOA -tyylinen
pinnan esitystarkkuus. Lisäksi listaa elementit jotka kannattaa tarkistaa Solibrissa.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import StructuralModel

_ASSOC_BAND = 50.0   # mm — tältä etäisyydeltä piste katsotaan kuuluvaksi pinnalle
_WALL_CONF_THR = 0.40
_OPENING_CONF_THR = 0.50
_COLUMN_CONF_THR = 0.45    # pilarin luottamus heijastaa nyt kompaktiutta (aspect)
_BEAM_CONF_THR = 0.35      # matalan luottamuksen palkki = mahd. kattokrääsä


def _ifc_mesh(ifc_path: Path, classes: tuple[str, ...]) -> o3d.geometry.TriangleMesh | None:
    import ifcopenshell
    import ifcopenshell.geom

    f = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    try:
        settings.set(settings.USE_WORLD_COORDS, True)
        settings.set(settings.CONVERT_BACK_UNITS, True)
    except Exception:
        settings.set("use-world-coords", True)
        settings.set("convert-back-units", True)

    verts: list[np.ndarray] = []
    tris: list[np.ndarray] = []
    offset = 0
    for cls in classes:
        for el in f.by_type(cls):
            if not el.Representation:
                continue
            shape = ifcopenshell.geom.create_shape(settings, el)
            v = np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
            t = np.array(shape.geometry.faces, dtype=np.int64).reshape(-1, 3)
            verts.append(v)
            tris.append(t + offset)
            offset += len(v)
    if not verts:
        return None
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.concatenate(verts))
    mesh.triangles = o3d.utility.Vector3iVector(np.concatenate(tris))
    return mesh


def _distances(cloud, mesh: o3d.geometry.TriangleMesh) -> np.ndarray:
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    pts = np.asarray(cloud.points, dtype=np.float32)
    return scene.compute_distance(o3d.core.Tensor(pts, dtype=o3d.core.Dtype.Float32)).numpy()


def _stats(dist: np.ndarray, tol: float) -> dict | None:
    assoc = dist[dist <= _ASSOC_BAND]
    if len(assoc) == 0:
        return None
    return {
        "points": int(len(assoc)),
        "within_tol_pct": round(100.0 * float((assoc <= tol).mean()), 1),
        "mean": round(float(assoc.mean()), 2),
        "median": round(float(np.median(assoc)), 2),
        "rms": round(float(np.sqrt(np.mean(assoc ** 2))), 2),
        "p95": round(float(np.percentile(assoc, 95)), 2),
        "max": round(float(assoc.max()), 2),
    }


def model_deviation(cloud, ifc_path: Path, tol: float = 2.5) -> dict:
    """Per-luokka (seinät/laatat) + kokonais-LOA pistepilveä vasten."""
    out: dict = {"tolerance_mm": tol, "by_class": {}}
    for label, classes in (("walls", ("IfcWall",)), ("slabs", ("IfcSlab",))):
        mesh = _ifc_mesh(ifc_path, classes)
        if mesh is None:
            continue
        s = _stats(_distances(cloud, mesh), tol)
        if s is not None:
            out["by_class"][label] = s
    full = _ifc_mesh(ifc_path, ("IfcWall", "IfcSlab"))
    if full is not None:
        s = _stats(_distances(cloud, full), tol)
        if s is not None:
            out["overall"] = s
    return out


_SF_BAND_EXTRA = 80.0   # mm — kaista pintojen ulkopuolelle
_SF_CORE = 60.0         # mm — kohinaikkuna pistepinnan mediaanin ympärillä


def wall_surface_accuracy(model: StructuralModel, cloud) -> list[dict]:
    """Per-seinä PINTAtarkkuus: skannatun pinnan mediaani vs mallin pinta.

    Erottaa mallin virheen pilven kohinasta: pistetason poikkeama (yllä oleva
    taulukko) sisältää skannerin kohinan (tyyp. 2–20 mm RMS) — pinnan MEDIAANI
    keskiarvoistaa sen pois ja kertoo todellisen mallinnustarkkuuden."""
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return []
    out: list[dict] = []
    for w in model.walls:
        if len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], float)
        p1 = np.array(w.axis[1], float)
        L = float(np.linalg.norm(p1 - p0))
        if L < 1.0:
            continue
        u = (p1 - p0) / L
        n = np.array([-u[1], u[0]])
        rel = pts[:, :2] - p0
        t = rel @ u
        perp = rel @ n
        zm = (pts[:, 2] > w.z_min + 200.0) & (pts[:, 2] < w.z_min + w.height - 200.0)
        band = zm & (t > 100.0) & (t < L - 100.0) & (np.abs(perp) < w.thickness / 2.0 + _SF_BAND_EXTRA)
        if band.sum() < 200:
            continue
        s = perp[band]
        side = s > 0
        dom = s[side] if side.sum() >= (~side).sum() else s[~side]
        med = float(np.median(dom))
        core = dom[np.abs(dom - med) < _SF_CORE]
        med = float(np.median(core)) if len(core) > 50 else med
        noise = float(np.sqrt(np.mean((core - med) ** 2))) if len(core) > 50 else float("nan")
        face = w.thickness / 2.0 if med > 0 else -w.thickness / 2.0
        out.append({
            "id": w.id,
            "face_err_mm": round(abs(med - face), 2),
            "noise_rms_mm": round(noise, 1),
        })
    return out


def flag_low_confidence(model: StructuralModel) -> list[dict]:
    """Elementit jotka kannattaa tarkistaa manuaalisesti Solibrissa."""
    flags: list[dict] = []
    for w in model.walls:
        if w.confidence < _WALL_CONF_THR:
            flags.append({"id": w.id, "type": "wall", "confidence": round(w.confidence, 3)})
    for op in getattr(model, "openings", []):
        if op.confidence < _OPENING_CONF_THR:
            flags.append({"id": op.id, "type": op.opening_type, "confidence": round(op.confidence, 3)})
    for col in getattr(model, "columns", None) or []:
        if col.confidence < _COLUMN_CONF_THR:
            flags.append({"id": col.id, "type": "column", "confidence": round(col.confidence, 3)})
    for bm in getattr(model, "beams", None) or []:
        if bm.confidence < _BEAM_CONF_THR:
            flags.append({"id": bm.id, "type": "beam", "confidence": round(bm.confidence, 3)})
    return flags


def write_qa_report(model: StructuralModel, cloud, ifc_path: Path, txt_path: Path, tol: float = 2.5) -> dict:
    dev = model_deviation(cloud, ifc_path, tol)
    flags = flag_low_confidence(model)

    lines: list[str] = []
    lines.append(f"scan2bim QA-raportti  —  {ifc_path.name}")
    lines.append(f"Toleranssi: {tol} mm")
    lines.append("")
    lines.append(f"Elementit: {len(model.walls)} seinaa, {len(model.slabs)} laattaa, "
                 f"{len(getattr(model, 'openings', []))} aukkoa")
    lines.append("")
    lines.append("Poikkeama pistepilvesta (pinnalle kuuluvat pisteet):")
    header = f"  {'luokka':<10}{'<=tol %':>9}{'keski':>8}{'med':>7}{'RMS':>8}{'p95':>8}{'max':>8}"
    lines.append(header)
    for label in ("walls", "slabs", "overall"):
        s = dev["by_class"].get(label) if label != "overall" else dev.get("overall")
        if not s:
            continue
        lines.append(f"  {label:<10}{s['within_tol_pct']:>8.1f}%{s['mean']:>8.2f}"
                     f"{s['median']:>7.2f}{s['rms']:>8.2f}{s['p95']:>8.2f}{s['max']:>8.2f}")
    surf = wall_surface_accuracy(model, cloud)
    surface_summary: dict | None = None
    if surf:
        lines.append("")
        lines.append("Pintatarkkuus (skannatun pinnan mediaani vs mallin pinta —")
        lines.append("pistetason hajonta yllä sisältää skannerin kohinan, tämä ei):")
        lines.append(f"  {'seina':<14}{'pinta mm':>9}{'kohina RMS':>12}")
        for r in surf:
            lines.append(f"  {r['id']:<14}{r['face_err_mm']:>9.2f}{r['noise_rms_mm']:>12.1f}")
        errs = [r["face_err_mm"] for r in surf]
        n_ok = sum(1 for e in errs if e <= 1.5)
        lines.append(f"  mediaani {np.median(errs):.2f} mm | <=1.5 mm: {n_ok}/{len(errs)} seinaa")
        noise = [r["noise_rms_mm"] for r in surf]
        surface_summary = {
            "median_mm": round(float(np.median(errs)), 2),
            "n_ok": n_ok, "n_total": len(errs),
            "noise_rms_mm": round(float(np.median(noise)), 1),
        }

    lines.append("")
    if flags:
        lines.append(f"TARKISTA MANUAALISESTI ({len(flags)} kpl, matala luottamus):")
        for fl in flags:
            lines.append(f"  - {fl['id']}  ({fl['type']}, conf {fl['confidence']})")
    else:
        lines.append("Ei matalan luottamuksen elementteja.")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return {"deviation": dev, "flags": flags, "surface": surface_summary}

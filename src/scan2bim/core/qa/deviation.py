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


def flag_low_confidence(model: StructuralModel) -> list[dict]:
    """Elementit jotka kannattaa tarkistaa manuaalisesti Solibrissa."""
    flags: list[dict] = []
    for w in model.walls:
        if w.confidence < _WALL_CONF_THR:
            flags.append({"id": w.id, "type": "wall", "confidence": round(w.confidence, 3)})
    for op in getattr(model, "openings", []):
        if op.confidence < _OPENING_CONF_THR:
            flags.append({"id": op.id, "type": op.opening_type, "confidence": round(op.confidence, 3)})
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
    lines.append("")
    if flags:
        lines.append(f"TARKISTA MANUAALISESTI ({len(flags)} kpl, matala luottamus):")
        for fl in flags:
            lines.append(f"  - {fl['id']}  ({fl['type']}, conf {fl['confidence']})")
    else:
        lines.append("Ei matalan luottamuksen elementteja.")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return {"deviation": dev, "flags": flags}

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
    pts_all = np.asarray(cloud.points)
    if len(pts_all) == 0:
        return []
    index = None
    if len(pts_all) >= 300_000 and len(model.walls) >= 3:
        from scan2bim.core.geometry.xy_index import XYIndex  # noqa: PLC0415
        index = XYIndex(pts_all)
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
        pts = pts_all
        if index is not None:
            from scan2bim.core.geometry.xy_index import subset  # noqa: PLC0415
            pts, _ = subset(pts_all, index, p0, u, n,
                            w.thickness / 2.0 + _SF_BAND_EXTRA, 100.0, L - 100.0)
            if len(pts) < 200:
                continue
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


_SUP_CELL = 200.0       # mm — pintaruudun koko peittoa laskettaessa
_SUP_THR = 0.15         # alle tämän = pinnalla ei ole tukea pilvessä
_SUP_MIN_PTS = 100      # pintahaun (`_nearest_surface`) oma minimi
_SUP_MIN_JUDGE = 10     # tätä vähemmällä seinän kaistassa ei ole mitään —
                        # EI kynnys tiheydelle, vaan "onko pisteitä lainkaan"


_CONT_COL = 500.0       # mm — sarakkeen leveys jatkuvuutta laskettaessa
_CONT_REL = 0.10        # sarake on tuettu jos siinä on tämä osuus sarakkeiden
                        # KESKIARVOSTA — suhteellinen, jotta harva skanni ei
                        # muuta aitoa seinää palkkilinjaksi
_CONT_MIN_WAIST = 10    # alle tämän vyötäröpisteen jatkuvuutta ei väitetä
_CONT_THR = 0.30        # alle tämän = ei yhtenäinen seinä vyötärökorkeudella
_WAIST_LO = 0.30        # vyötärökaista osuutena seinän korkeudesta — lattia ja
_WAIST_HI = 0.70        # katto rajautuvat pois, seinä erottuu roinasta


def _wall_support(w, pts_all: np.ndarray, index) -> tuple[float, float] | None:
    """(pintatuki, vyötärön jatkuvuus) — molemmat 0..1, samasta kaistaskannauksesta.

    PINTATUKI: kuinka suuri osa seinän pinnasta on keilattu. Haamuseinä ei saa
    pinnalleen pisteitä.

    JATKUVUUS: kuinka moni 500 mm sarake on tuettu VYÖTÄRÖKORKEUDELLA (30–70 %).
    Tämä erottaa PALKKILINJAN seinästä: histogrammidetektori tekee palkiston
    keskikorkeuden tiheydestä 28 m "seiniä", ja niillä on pisteitä joka
    korkeudella (lattia, katto, palkki, pilarit) — mutta vyötäröllä vain
    pilarit 8 m välein. Mitattu Rohbau-GT:llä: 6 aitoa seinää 0.50–1.00,
    6 palkkiseinää 0.05–0.07. Pystytuki EI erottele (aidot 0.63–0.94,
    palkkiseinät 0.92–1.00 — päinvastoin kuin intuitio sanoo).
    """
    if len(w.axis) < 2:
        return None
    p0 = np.array(w.axis[0], float)
    p1 = np.array(w.axis[1], float)
    L = float(np.linalg.norm(p1 - p0))
    if L < 1.0 or w.height < 1.0:
        return None
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    half = w.thickness / 2.0 + 2.5 * _SF_BAND_EXTRA

    pts = pts_all
    if index is not None:
        from scan2bim.core.geometry.xy_index import subset  # noqa: PLC0415
        pts, _ = subset(pts_all, index, p0, u, n, half, 0.0, L)
        if len(pts) < _SUP_MIN_JUDGE:
            return 0.0, 0.0

    rel = pts[:, :2] - p0
    t = rel @ u
    perp = rel @ n
    z = pts[:, 2]
    near = ((t > 0.0) & (t < L) & (np.abs(perp) < half)
            & (z > w.z_min + 100.0) & (z < w.z_min + w.height - 100.0))
    if near.sum() < _SUP_MIN_JUDGE:
        return 0.0, 0.0
    t, perp, z = t[near], perp[near], z[near]

    face = np.abs(np.abs(perp) - w.thickness / 2.0) < _SF_BAND_EXTRA
    if face.sum() < _SUP_MIN_JUDGE:
        return 0.0, 0.0
    side = perp[face] > 0
    dom = perp[face][side] if side.sum() >= (~side).sum() else perp[face][~side]
    med = float(np.median(dom))

    on = np.abs(perp - med) < _SF_BAND_EXTRA
    nt = max(1, int(L / _SUP_CELL))
    nz = max(1, int(w.height / _SUP_CELL))
    ti = np.clip((t[on] / L * nt).astype(np.int64), 0, nt - 1)
    zi = np.clip(((z[on] - w.z_min) / w.height * nz).astype(np.int64), 0, nz - 1)
    support = float(len(np.unique(ti * nz + zi))) / float(nt * nz)

    zr = (z[on] - w.z_min) / w.height
    waist = (zr > _WAIST_LO) & (zr < _WAIST_HI)
    ncol = max(1, int(L / _CONT_COL))
    if waist.sum() < _CONT_MIN_WAIST:
        return support, None
    ci = np.clip((t[on][waist] / L * ncol).astype(np.int64), 0, ncol - 1)
    cnt = np.bincount(ci, minlength=ncol)
    return support, _column_continuity(cnt)


def _column_continuity(cnt: np.ndarray) -> float:
    """Osuus sarakkeista joissa on pintaa — KEILAUSTIHEYDESTÄ riippumatta.

    Kiinteä raja (ennen: 5 pistettä/sarake) sitoo mittarin skannin tiheyteen:
    mitattu Rohbaulla, että 1/250 harvennus poisti kaksi GT-aitoa seinää, ja
    synteettisesti erottelu aito−palkki romahti 0.94 → 0.00 samalla kun
    suhteellinen sääntö piti sen 0.79:ssä. Palkkilinja erottuu yhä, koska sen
    pisteet kasautuvat pilarisarakkeisiin: keskiarvo nousee ja tyhjät sarakkeet
    jäävät tyhjiksi.
    """
    thr = max(1.0, _CONT_REL * float(cnt.mean()))
    return float((cnt >= thr).mean())


_SUP_SEEK = 1000.0      # mm — kuinka kaukaa etsitään todellista pintaa
_SUP_BAND = 60.0        # mm — kaista huipun ympärillä jatkuvuutta laskettaessa


def _nearest_surface(w, pts_all: np.ndarray, index) -> float | None:
    """Onko seinä VÄÄRÄSSÄ PAIKASSA vai onko sitä ollenkaan?

    Palauttaa etäisyyden mallin pinnalta lähimpään todelliseen pintakeskittymään,
    tai None jos mitään ei ole. Ero ratkaisee toimenpiteen: siirrä vai poista.

    Etsitään VYÖTÄRÖKORKEUDELTA ja vaaditaan JATKUVA huippu — samoin kuin
    jatkuvuus ja napsautus mittaavat. Koko korkeudelta haettuna löytyy lattian
    ja katon roina: mitattu Rohbaussa (kerros 10 m), jossa kaksi haamua sai
    näin offsetin 442 ja 825 mm vaikka vyötäröllä ei ollut yhtään pistettä,
    eikä siirtymäraja enää erottanut niitä aidosta siirtyneestä seinästä.
    Aidolla lyhyellä seinällä (`wall_ext_008`) vyötäröllä on 63 754 pistettä.
    """
    p0 = np.array(w.axis[0], float)
    p1 = np.array(w.axis[1], float)
    L = float(np.linalg.norm(p1 - p0))
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])

    pts = pts_all
    if index is not None:
        from scan2bim.core.geometry.xy_index import subset  # noqa: PLC0415
        pts, _ = subset(pts_all, index, p0, u, n, _SUP_SEEK, 0.0, L)
    if len(pts) < _SUP_MIN_PTS:
        return None
    rel = pts[:, :2] - p0
    t = rel @ u
    perp = rel @ n
    z = pts[:, 2]
    sel = ((t > 0.0) & (t < L) & (np.abs(perp) < _SUP_SEEK)
           & (z > w.z_min + _WAIST_LO * w.height) & (z < w.z_min + _WAIST_HI * w.height))
    if sel.sum() < _SUP_MIN_PTS:
        return None
    hist, edges = np.histogram(perp[sel], bins=40, range=(-_SUP_SEEK, _SUP_SEEK))
    peak = 0.5 * (edges[hist.argmax()] + edges[hist.argmax() + 1])
    on = np.abs(perp[sel] - peak) < _SUP_BAND
    ncol = max(1, int(L / _CONT_COL))
    ci = np.clip((t[sel][on] / L * ncol).astype(int), 0, ncol - 1)
    if _column_continuity(np.bincount(ci, minlength=ncol)) < _CONT_THR:
        return None
    return round(abs(abs(float(peak)) - w.thickness / 2.0), 1)


def measure_wall_support(model: StructuralModel, cloud) -> None:
    """Kirjaa jokaiselle seinälle MITATUN pintatuen (`Wall.support`)."""
    pts_all = np.asarray(cloud.points)
    if len(pts_all) == 0:
        return
    index = None
    if len(pts_all) >= 300_000 and len(model.walls) >= 3:
        from scan2bim.core.geometry.xy_index import XYIndex  # noqa: PLC0415
        index = XYIndex(pts_all)
    for w in model.walls:
        res = _wall_support(w, pts_all, index)
        if res is None:
            w.support = w.continuity = w.support_offset = None
            continue
        s, c = res
        w.support = round(s, 3)
        w.continuity = None if c is None else round(c, 3)
        w.support_offset = None
        if (s < _SUP_THR or c < _CONT_THR) and len(w.axis) >= 2:
            w.support_offset = _nearest_surface(w, pts_all, index)


def flag_low_confidence(model: StructuralModel) -> list[dict]:
    """Elementit jotka kannattaa tarkistaa manuaalisesti Solibrissa.

    Seinillä ratkaisee MITATTU pintatuki jos se on laskettu; detektorin oma
    `confidence` on kokoproxy (pituus) eikä se erota valeseinää aidosta.
    """
    flags: list[dict] = []
    for w in model.walls:
        if w.support is not None:
            weak = w.support < _SUP_THR
            broken = w.continuity is not None and w.continuity < _CONT_THR
            if weak or broken:
                if w.support_offset is not None and w.support_offset >= 100.0:
                    why = f"pinta {w.support_offset:.0f} mm sivussa — siirrä tai poista"
                elif broken and not weak:
                    why = (f"ei yhtenäinen seinä ({w.continuity * 100:.0f} % vyötäröstä) "
                           "— mahdollinen palkki- tai pilarilinja")
                else:
                    why = f"ei pintaa pilvessä ({w.support * 100:.0f} % keilattu)"
                flags.append({"id": w.id, "type": "wall", "confidence": round(w.confidence, 3),
                              "support": w.support, "continuity": w.continuity,
                              "offset_mm": w.support_offset, "reason": why})
        elif w.confidence < _WALL_CONF_THR:
            flags.append({"id": w.id, "type": "wall", "confidence": round(w.confidence, 3),
                          "reason": "detektorin luottamus matala"})
    for op in getattr(model, "openings", []):
        if op.confidence < _OPENING_CONF_THR:
            flags.append({"id": op.id, "type": op.opening_type, "confidence": round(op.confidence, 3),
                          "reason": "aukko pieni tai heikosti rajattu"})
    for col in getattr(model, "columns", None) or []:
        if col.confidence < _COLUMN_CONF_THR:
            flags.append({"id": col.id, "type": "column", "confidence": round(col.confidence, 3),
                          "reason": "pitkänomainen tai harva — ei kompakti pilari"})
    for bm in getattr(model, "beams", None) or []:
        if bm.confidence < _BEAM_CONF_THR:
            flags.append({"id": bm.id, "type": "beam", "confidence": round(bm.confidence, 3),
                          "reason": "heikko palkki — mahdollista kattokrääsää"})
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

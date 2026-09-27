"""Jaljita miksi perimetri luo tukemattoman seinan: logita kontuurireunat,
push-arvo ja _edge_covered-paatos oikeasta tuotantoajosta."""
from pathlib import Path
import numpy as np

import scan2bim.core.semantics.perimeter as PM

_orig = PM.add_perimeter_walls
LOG = []


def traced(boundary, existing, z_min, height, pts=None):
    simp = PM._simplify_boundary(boundary) if boundary and len(boundary) >= 3 else boundary
    rec = {"n_raw": len(boundary or []), "n_simp": len(simp or []),
           "z_min": z_min, "height": height, "simp": simp,
           "existing": [(w.id, [list(map(float, p)) for p in w.axis], w.thickness) for w in existing]}
    # reunakohtainen paatos
    if simp and len(simp) >= 3:
        verts = [np.array(p, float) for p in simp]
        n = len(verts)
        area2 = sum(verts[i][0]*verts[(i+1) % n][1] - verts[(i+1) % n][0]*verts[i][1] for i in range(n))
        ccw = area2 > 0.0
        high = None
        if pts is not None and len(pts):
            arr = np.asarray(pts)
            high = arr[arr[:, 2] >= z_min + PM._BEYOND_Z_FRAC * height]
        edges = []
        for i in range(n):
            a, b = verts[i], verts[(i+1) % n]
            seg = b - a
            L = float(np.linalg.norm(seg))
            if L < PM._MIN_EDGE:
                edges.append((i, L, "SHORT", None, None)); continue
            u = seg / L
            cov = PM._edge_covered(a, b, u, L, existing)
            nv = np.array([-u[1], u[0]])
            near = []
            for w2 in existing:
                q0 = np.asarray(w2.axis[0], float); q1 = np.asarray(w2.axis[1], float)
                dd = q1 - q0; wl = float(np.linalg.norm(dd))
                if wl < 1: continue
                wu = dd / wl
                if abs(float(wu @ u)) < 0.90: continue
                perp = abs(float((q0 - a) @ nv))
                t0 = float((q0 - a) @ u); t1 = float((q1 - a) @ u)
                ov = min(max(t0, t1), L) - max(min(t0, t1), 0.0)
                if perp < 1200:
                    near.append(f"{w2.id}(perp={perp:.0f},ov={ov/L:.2f},L={wl:.0f})")
            print(f"      reuna{i} L={L:.0f} cov={cov} lahella: {near}", flush=True)
            nrm = np.array([u[1], -u[0]]) if ccw else np.array([-u[1], u[0]])
            push = PM._ceiling_extent_beyond(a, u, nrm, L, high) if high is not None else 0.0
            # pistetuki: montako pistetta kaistassa |perp| < 250 keskikorkeudella
            supp = -1
            if pts is not None and len(pts):
                arr = np.asarray(pts)
                mz = (arr[:, 2] > z_min + 400) & (arr[:, 2] < z_min + height - 300)
                rel = arr[mz, :2] - a
                al = rel @ u; pp = rel @ nrm
                supp = int(((al > 0) & (al < L) & (np.abs(pp) < 250)).sum())
            edges.append((i, L, "COVERED" if cov else "NEW", push, supp,
                          [round(float(a[0])), round(float(a[1]))],
                          [round(float(b[0])), round(float(b[1]))]))
        rec["edges"] = edges
    LOG.append(rec)
    return _orig(boundary, existing, z_min, height, pts=pts)


PM.add_perimeter_walls = traced
import scan2bim.core.pipeline as PL  # noqa: E402  (import jalkeen patchin)
PL.__dict__.setdefault("_", None)

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402

paths = [Path(r"C:\Users\lauri\Downloads\aligned_low_apartment\apt.ply")]
cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                     export_dxf=False, export_qa=False,
                     semantic_filter_mode="pointnet")
out = Path(r"C:\Users\lauri\scan2bim\data\output\_perim_trace_apt2")
models = Pipeline(cfg).run_floors(paths, out)

print("\n\n===== PERIMETRI-JALJITYS =====")
for k, rec in enumerate(LOG):
    print(f"\n--- kutsu {k}: kontuuri {rec['n_raw']} -> {rec['n_simp']} karkea, "
          f"z_min={rec['z_min']:.0f} h={rec['height']:.0f}, existing={len(rec['existing'])}")
    for e in rec.get("edges", []):
        if e[2] == "SHORT":
            continue
        print(f"  reuna {e[0]:2d} L={e[1]:7.0f} {e[2]:8s} push={e[3]:7.1f} tuki={e[4]:8d} "
              f"a={e[5]} b={e[6]}")
for m in models:
    print(f"\nRESULT walls={len(m.walls)}")
    for w in m.walls:
        if w.source.method == "floorplan":
            print("  FLOORPLAN", w.id, w.axis, w.thickness)

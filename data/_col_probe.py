"""PILARIPORTIT: mika portti hylkaa mitkakin GT-pilarit.

detect_columns hylkaa ehdokkaan kahdeksassa eri kohdassa. Pelkka lopputulos
("24/34") ei kerro MITA korjata. Tama ajaa saman silmukan mutta kirjaa jokaisen
hylkayksen syyn ja mittaluvut, ja tasmaa ne ground-truthin pilareihin.

Vaihe 1 (kerran, ~9 min):  _col_probe.py cache <pilvi.ply>
   Ajaa putken ja tallentaa detect_columns:n SYOTTEET (pilvi, seinat, z:t).
Vaihe 2 (sekunteja, toistettavissa):  _col_probe.py gates <pilvi.ply>
   Lukee valimuistin ja tulostaa porttitaulukon.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_SEM = "pointnet"   # 3DSES ajettiin ilman suodatinta: aseta "off"

# .npz eika pickle: valimuistiin ei tarvita muuta kuin taulukoita, eika
# koodinsuoritusta salliva formaatti ansaitse paikkaansa tyokalussa.
def _cache_path(cloud_path: Path) -> Path:
    return Path("data") / f"_col_cache_{cloud_path.stem}.npz"


def _cache(cloud_path: Path) -> None:
    cache = _cache_path(cloud_path)
    import ordinate.core.segmentation.column_detector as CD
    from ordinate.core.pipeline import Pipeline, PipelineConfig

    real = CD.detect_columns
    saved = {}

    def spy(cloud, walls, floor_z, ceiling_z):
        if not saved:
            saved["done"] = True
            pts = np.asarray(cloud.points)
            ax = np.array([[list(w.axis[0]), list(w.axis[1])] for w in walls], float)
            th = np.array([float(w.thickness) for w in walls])
            np.savez(cache, pts=pts, wall_axes=ax, wall_t=th,
                     zs=np.array([floor_z, ceiling_z], float))
            print(f"valimuisti: {len(pts):,} pistetta, {len(walls)} seinaa, "
                  f"z {floor_z:.0f}..{ceiling_z:.0f}", flush=True)
        return real(cloud, walls, floor_z, ceiling_z)

    CD.detect_columns = spy
    import ordinate.core.pipeline as P
    P.detect_columns = spy   # jos pipeline importtasi nimen suoraan
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False,
                         semantic_filter_mode=_SEM)
    Pipeline(cfg).run_floors([cloud_path], Path("data/output/_col_probe"))


def _gates(cloud_path: Path) -> None:
    import ordinate.core.segmentation.column_detector as CD
    from scipy.ndimage import label as _cc_label
    from scipy.spatial import cKDTree
    import json

    s = np.load(_cache_path(cloud_path))
    pts = s["pts"]
    floor_z, ceiling_z = float(s["zs"][0]), float(s["zs"][1])
    room_h = ceiling_z - floor_z

    gt = json.load(open(str(cloud_path) + ".gt.json"))
    gt_xy = np.array([[c[0], c[1]] for c in gt["columns"]], float)

    class _W:
        def __init__(self, axis, t): self.axis, self.thickness = axis, t
    walls = [_W([list(a[0]), list(a[1])], float(t))
             for a, t in zip(s["wall_axes"], s["wall_t"])]

    zmask = (pts[:, 2] > floor_z + CD._Z_MARGIN) & (pts[:, 2] < ceiling_z - CD._Z_MARGIN)
    band = pts[zmask]
    far = CD._dist_to_walls(band[:, :2], walls) > CD._WALL_MARGIN
    free = band[far]

    _xytree = cKDTree(pts[::4, :2]) if len(pts) > 4000 else None
    _wm = (pts[:, 2] > floor_z + CD._WAIST_LO) & (pts[:, 2] < floor_z + CD._WAIST_HI)
    waist_pts = pts[_wm, :2] if int(_wm.sum()) > 200 else None
    waist_tree = cKDTree(waist_pts) if waist_pts is not None else None

    x0, y0 = float(free[:, 0].min()), float(free[:, 1].min())
    ix = ((free[:, 0] - x0) / CD._CELL_MM).astype(np.int64)
    iy = ((free[:, 1] - y0) / CD._CELL_MM).astype(np.int64)
    z_lo = floor_z + CD._Z_MARGIN
    iz = ((free[:, 2] - z_lo) / CD._ZBIN_MM).astype(np.int64)
    nx, ny = int(ix.max()) + 1, int(iy.max()) + 1
    nz = max(int((ceiling_z - CD._Z_MARGIN - z_lo) / CD._ZBIN_MM), 1)
    iz = np.clip(iz, 0, nz - 1)
    flat = (ix * ny + iy) * nz + iz
    counts = np.bincount(flat, minlength=nx * ny * nz).reshape(nx, ny, nz)
    cand = (counts >= 2).sum(axis=2) / nz >= CD._VFILL_MIN
    labels, ncomp = _cc_label(cand, structure=np.ones((3, 3), dtype=int))

    rows = []
    for k in range(1, ncomp + 1):
        cx_c, cy_c = np.nonzero(labels == k)
        ext = max((cx_c.max() - cx_c.min() + 1), (cy_c.max() - cy_c.min() + 1)) * CD._CELL_MM
        cxm = x0 + (cx_c.mean() + 0.5) * CD._CELL_MM
        cym = y0 + (cy_c.mean() + 0.5) * CD._CELL_MM
        r = {"xy": (cxm, cym), "ext": ext, "reject": None}
        if not (CD._COMP_MIN_MM <= ext <= CD._COMP_MAX_MM):
            r["reject"] = f"ext {ext:.0f}"
            rows.append(r); continue
        rx0 = max(cx_c.min() - CD._RING_OUT, 0); rx1 = min(cx_c.max() + CD._RING_OUT + 1, nx)
        ry0 = max(cy_c.min() - CD._RING_OUT, 0); ry1 = min(cy_c.max() + CD._RING_OUT + 1, ny)
        ring = cand[rx0:rx1, ry0:ry1].copy()
        i0 = max(cx_c.min() - CD._RING_IN, 0); i1 = min(cx_c.max() + CD._RING_IN + 1, nx)
        j0 = max(cy_c.min() - CD._RING_IN, 0); j1 = min(cy_c.max() + CD._RING_IN + 1, ny)
        ring[i0 - rx0:i1 - rx0, j0 - ry0:j1 - ry0] = False
        r["ring"] = int(ring.sum())
        if r["ring"] >= CD._RING_MAX_CELLS:
            r["reject"] = f"ring {r['ring']}"
            rows.append(r); continue
        in_c = ((ix >= cx_c.min() - 1) & (ix <= cx_c.max() + 1)
                & (iy >= cy_c.min() - 1) & (iy <= cy_c.max() + 1))
        cl = free[in_c]
        if len(cl) < CD._MIN_CLUSTER_PTS:
            r["reject"] = f"pts {len(cl)}"; rows.append(r); continue
        zext = float(cl[:, 2].max() - cl[:, 2].min())
        if zext < min(CD._MIN_HEIGHT_FRAC * room_h, CD._MIN_ABS_HEIGHT):
            r["reject"] = f"zext {zext:.0f}"; rows.append(r); continue
        xy = cl[:, :2]
        wx = float(np.percentile(xy[:, 0], 98) - np.percentile(xy[:, 0], 2))
        wy = float(np.percentile(xy[:, 1], 98) - np.percentile(xy[:, 1], 2))
        fp = max(wx, wy)
        r["fp"] = fp
        if not (CD._MIN_FOOTPRINT <= fp <= CD._MAX_FOOTPRINT) or fp < CD._MIN_REAL_FOOTPRINT:
            r["reject"] = f"fp {fp:.0f}"; rows.append(r); continue
        asp = fp / max(min(wx, wy), 1.0)
        r["aspect"] = asp
        if asp > CD._MAX_ASPECT:
            r["reject"] = f"aspect {asp:.2f}"; rows.append(r); continue
        cx = float(xy[:, 0].mean()); cy = float(xy[:, 1].mean())
        r["xy"] = (cx, cy)
        probes = np.column_stack([cx + 1000.0 * np.cos(np.linspace(0, 2 * np.pi, 8, endpoint=False)),
                                  cy + 1000.0 * np.sin(np.linspace(0, 2 * np.pi, 8, endpoint=False))])
        d, _ = _xytree.query(probes, k=1)
        if int((d < 600.0).sum()) < 5:
            r["reject"] = "surrounded"; rows.append(r); continue
        if not CD._cross_section_stable(cl, floor_z, ceiling_z):
            r["reject"] = "xsection"; rows.append(r); continue
        # sektorit + suurin yhtenainen VAPAA kaari
        nsec, arc = _sectors(cx, cy, fp, waist_pts, waist_tree)
        r["sect"] = nsec
        r["free_arc"] = arc
        r["gap"], r["near"] = _gap(cx, cy, wx, wy, waist_pts, waist_tree)
        if nsec > CD._MAX_SECTOR_COVER:
            r["reject"] = f"waist sect={nsec} vapaa_kaari={arc:.0f}deg"
            rows.append(r); continue
        rows.append(r)

    # tasmaa GT:hen
    print(f"komponentteja {len(rows)}, GT-pilareita {len(gt_xy)}\n")
    hit = np.zeros(len(gt_xy), bool)
    for r in rows:
        c = np.array(r["xy"])
        dd = np.linalg.norm(gt_xy - c, axis=1)
        j = int(np.argmin(dd))
        r["gt"] = j if dd[j] < 800.0 else -1
        if r["gt"] >= 0 and r["reject"] is None:
            hit[j] = True
    acc = [r for r in rows if r["reject"] is None]
    print(f"HYVAKSYTTY {len(acc)}  (GT-osumia {int(hit.sum())}/{len(gt_xy)})")
    print(f"VAARIA POSITIIVISIA (ei GT:ta): {sum(1 for r in acc if r['gt'] < 0)}\n")
    from collections import Counter
    miss = [r for r in rows if r["reject"] and r["gt"] >= 0]
    print(f"GT-pilareita hylatty: {len(miss)}")
    print(Counter(r["reject"].split()[0] for r in miss).most_common())
    print("\nesimerkit (GT-pilari jonka portti hylkasi):")
    for r in miss[:12]:
        print(f"  GT{r['gt']:2d} ({r['xy'][0]:8.0f},{r['xy'][1]:8.0f}) -> {r['reject']}")
    print("\n=== EROTTELU: rako pilarin kulmasateen takana / lahirenkaan sektorit ===")
    print(f"{'ryhma':28}{'n':>4}{'rako mm (min/med/max)':>26}{'lahi-sekt max':>15}")

    def _stat(rs, name):
        g = [r["gap"] for r in rs if "gap" in r and np.isfinite(r["gap"])]
        nr = [r["near"] for r in rs if "near" in r]
        if not g:
            print(f"{name:28}{len(rs):>4}{'-':>26}{'-':>15}"); return
        print(f"{name:28}{len(rs):>4}"
              f"{min(g):>8.0f}{np.median(g):>9.0f}{max(g):>9.0f}"
              f"{(max(nr) if nr else 0):>15}")

    _stat([r for r in rows if r["gt"] >= 0 and r["reject"] is None], "GT-pilari, hyvaksytty")
    _stat([r for r in rows if r["gt"] >= 0 and r["reject"]], "GT-pilari, HYLATTY")
    _stat([r for r in rows if r["gt"] < 0 and "gap" in r], "ei-GT (paasi waist-portille)")
    print("\nGT-pilari joka hylattiin, yksitellen:")
    for r in miss:
        print(f"  GT{r['gt']:2d} sect={r.get('sect','?'):2} rako={r.get('gap',-1):6.0f} mm "
              f"lahi-sekt={r.get('near','?')}")


def _gap(cx, cy, wx, wy, waist_pts, waist_tree):
    """Saateittainen RAKO: kuinka kaukana lahin vyotarokorkeuden piste on
    pilarin OMAN kulmasateen ulkopuolella, ja montako sektoria on tayttynyt
    heti kulmasateen takana (lahirengas).

    Aito pilari seisoo vapaana: rako on aisleleveyden verran vaikka hylly
    olisi 320 mm paassa. Seinanpatka jatkuu linjassaan -> rako ~0."""
    if waist_tree is None:
        return float("inf"), 0
    r_corner = float(np.hypot(wx / 2.0, wy / 2.0))
    idx = waist_tree.query_ball_point([cx, cy], r_corner + 700.0)
    if not idx:
        return float("inf"), 0
    rel = waist_pts[idx] - np.array([cx, cy])
    d = np.hypot(rel[:, 0], rel[:, 1])
    out = d > r_corner
    if not out.any():
        return float("inf"), 0
    gap = float(d[out].min() - r_corner)
    near = out & (d <= r_corner + 150.0)
    if not near.any():
        return gap, 0
    ang = np.arctan2(rel[near, 1], rel[near, 0]) % (2 * np.pi)
    sec = (ang / (2 * np.pi) * 24).astype(int) % 24
    return gap, int(len(np.unique(sec)))


def _sectors(cx, cy, fp, waist_pts, waist_tree):
    """(taysien sektorien maara, suurin yhtenainen VAPAA kaari asteina)."""
    import ordinate.core.segmentation.column_detector as CD
    if waist_tree is None:
        return 0, 360.0
    r_out = fp / 2.0 + CD._SECTOR_RING_OUT
    idx = waist_tree.query_ball_point([cx, cy], r_out)
    if not idx:
        return 0, 360.0
    rel = waist_pts[idx] - np.array([cx, cy])
    d = np.hypot(rel[:, 0], rel[:, 1])
    band = (d >= fp / 2.0 + CD._SECTOR_RING_IN) & (d <= r_out)
    if not band.any():
        return 0, 360.0
    ang = np.arctan2(rel[band, 1], rel[band, 0]) % (2 * np.pi)
    sec = (ang / (2 * np.pi) * CD._SECTOR_N).astype(int) % CD._SECTOR_N
    occ = np.zeros(CD._SECTOR_N, bool)
    occ[np.unique(sec)] = True
    n = int(occ.sum())
    if n == 0:
        return 0, 360.0
    # suurin yhtenainen vapaa jakso ympyralla
    best = run = 0
    for i in range(2 * CD._SECTOR_N):
        if not occ[i % CD._SECTOR_N]:
            run += 1; best = max(best, min(run, CD._SECTOR_N))
        else:
            run = 0
    return n, best * 360.0 / CD._SECTOR_N


if __name__ == "__main__":
    mode, cloud = sys.argv[1], Path(sys.argv[2])
    if len(sys.argv) > 3:
        _SEM = sys.argv[3]   # 3DSES ajettiin ilman suodatinta
    (_cache if mode == "cache" else _gates)(cloud)

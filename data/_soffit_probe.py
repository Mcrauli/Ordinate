"""Palkkimalli 2: SOFFIT, ei pisteklusteri.

Nykyinen detektori klusteroi kattokaistan pisteet XY:ssa ja lukee palkin
leveyden klusterin XY-laajuudesta. Skannattu palkki ei ole umpikappale vaan
kaksi pystypintaa + alapinta, joten klusterin leveys on joko ~0 (yksi pinta,
mitattu retail 143 mm -> hylky FINISHED_MIN 150) tai koko palkisto (mitattu
retail 47 m -> hylky MAX_WIDTH 600). Kumpikaan ei ole palkin leveys.

Tama mittaa toisen mallin: alapinnan korkeuskartta. Jokaiselle XY-solulle
kattokaistan ALIN piste = sen kohdalla roikkuvan kappaleen alapinta. Vierekkaiset
samankorkeat solut = yksi soffit-laikku. Laikun leveys ON palkin leveys.

Ajo: _soffit_probe.py <cloud.ply|coord.npy> <model.json> [class.npy]
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

_CELL = 200.0        # mm — soffit-kartan solu
_MIN_PTS = 3         # pisteita solussa jotta alapinta on mitattu
_Z_TOL = 150.0       # mm — naapurisolu samaa laikkua jos alapinta talla valilla
_MAX_DEPTH = 3000.0  # mm — kuinka syvalta katosta soffitteja etsitaan
_MIN_CELLS = 8
_OFF = 500_000       # negatiiviset solukoordinaatit positiivisiksi ennen avainta
_BASE = 1_000_003
_REG = {
    0: "None", 1: "Ceiling", 2: "Slanted Ceiling", 3: "Ceiling Cutout", 4: "Floor",
    5: "Wall", 6: "Drywall", 7: "Wall Cutout", 8: "Parapet", 9: "Beam", 10: "Column",
    11: "Staircase", 12: "Window Cutout", 13: "Window", 14: "Door Rough Opening",
    15: "Facade Element", 16: "Elevator Doors", 17: "TGA",
}


def load_pts(path: str) -> np.ndarray:
    if path.endswith(".npy"):
        p = np.load(path).astype(np.float64)
    else:
        import open3d as o3d
        p = np.asarray(o3d.io.read_point_cloud(path).points, dtype=np.float64)
    if np.ptp(p[:, 0]) < 500.0:
        p = p * 1000.0
    return p


def soffit_map(pts: np.ndarray, z_lo: float, z_hi: float, z_free: float | None = None):
    """XY-solu -> (alin z, pistemaara).

    z_lo on ALARAJA MITTAUKSELLE (lattian ylapuolelta), z_free se korkeus jonka
    ylapuolella alapinnan on oltava jotta solu on soffit. Nain seina, pilari,
    hylly ja gondoli putoavat itsestaan: niiden alin piste on lattian lahella.
    """
    m = (pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)
    q = pts[m]
    if not len(q):
        return {}, m
    ij = np.floor(q[:, :2] / _CELL).astype(np.int64) + _OFF
    assert ij.min() >= 0 and ij.max() < _OFF * 2, "solukoordinaatti ulkona avaruudesta"
    key = ij[:, 0] * _BASE + ij[:, 1]
    order = np.argsort(key, kind="stable")
    key_s, z_s = key[order], q[order, 2]
    bounds = np.flatnonzero(np.diff(key_s)) + 1
    starts = np.concatenate([[0], bounds])
    ends = np.concatenate([bounds, [len(key_s)]])
    out = {}
    for s, e in zip(starts, ends):
        if e - s < _MIN_PTS:
            continue
        zb = float(z_s[s:e].min())
        if z_free is not None and zb < z_free:
            continue
        out[int(key_s[s])] = (zb, e - s)
    return out, m


def patches(cells: dict):
    """Yhtenaiset laikut: naapuri (4-yhteys) ja alapinta _Z_TOL:n sisalla."""
    seen = set()
    for k0 in cells:
        if k0 in seen:
            continue
        z0 = cells[k0][0]
        stack, comp = [k0], []
        seen.add(k0)
        while stack:
            k = stack.pop()
            comp.append(k)
            i, j = divmod(k, _BASE)
            z = cells[k][0]
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (i + di) * _BASE + (j + dj)
                if n not in cells or n in seen:
                    continue
                zn = cells[n][0]
                # naapuriehto JA ankkuriehto: ilman jalkimmaista laikku ryomii
                # portaittain lapi koko mallin (mitattu: 200 m "palkki")
                if abs(zn - z) <= _Z_TOL and abs(zn - z0) <= _Z_TOL:
                    seen.add(n)
                    stack.append(n)
        if len(comp) >= _MIN_CELLS:
            yield comp


def main(cloud_path: str, model_json: str, class_npy: str | None = None) -> None:
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 3000)
    pts = load_pts(cloud_path)
    C = np.load(class_npy).ravel() if class_npy else None

    z_hi = zc - 30.0
    z_lo = zf + 200.0
    z_free = max(zf + 0.5 * (zc - zf), zc - _MAX_DEPTH)
    cells, band = soffit_map(pts, z_lo, z_hi, z_free)
    print(f"lattia {zf:.0f} katto {zc:.0f}  mittaus {z_lo:.0f}..{z_hi:.0f}  "
          f"soffit-raja {z_free:.0f}  pisteita {int(band.sum()):,}  soluja {len(cells):,}")

    if C is not None:
        Cb = C[band]
    rows = []
    for comp in patches(cells):
        ij = np.array([divmod(k, _BASE) for k in comp], float) - _OFF
        xy = ij * _CELL + _CELL / 2
        z = np.array([cells[k][0] for k in comp])
        n = sum(cells[k][1] for k in comp)
        c = xy.mean(0)
        A = xy - c
        _, V = np.linalg.eigh(A.T @ A / len(A))
        u = V[:, 1]
        L = float((A @ u).ptp()) + _CELL
        W = float((A @ V[:, 0]).ptp()) + _CELL
        rows.append((n, L, W, float(np.median(z)), float(z.std()), c, u, len(comp)))

    rows.sort(key=lambda r: -r[0])
    print(f"\n{'n':>9s} {'pituus':>7s} {'lev':>6s} {'alapinta':>9s} {'z-sd':>5s} "
          f"{'syvyys':>6s} {'asp':>5s}  GT")
    for n, L, W, zb, zsd, c, u, ncell in rows[:25]:
        gt = ""
        if C is not None:
            nrm = np.array([-u[1], u[0]])
            d = pts[band][:, :2] - c
            sel = ((np.abs(d @ u) < L / 2) & (np.abs(d @ nrm) < W / 2)
                   & (pts[band][:, 2] < zb + 400))
            if sel.sum():
                cnt = collections.Counter(Cb[sel].tolist())
                gt = "  ".join(f"{_REG.get(k, k)}={100 * v / sel.sum():.0f}%"
                              for k, v in cnt.most_common(3))
        print(f"{n:9d} {L:7.0f} {W:6.0f} {zb:9.0f} {zsd:5.0f} {zc - zb:6.0f} "
              f"{L / max(W, 1):5.1f}  {gt}")
    print(f"laikkuja yhteensa {len(rows)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])

"""PROTOTYYPPI: seinat suoraan pystypinnoista, ei lattiakontuurista.

Nykyiset detektorit lahtevat lattiasta (contour) tai pohjan tiheysprojektiosta
(histogram). Molemmat olettavat etta lattia nakyy ja etta pohja on avoin.
Matalassa sokkeloisessa kellarissa kumpikaan ei pade: mitattu kattavuus 0.009
(histogram) ja 0.045 (contour), kun pystypintapisteita on 673 556.

Tama lahtee siita mika seinassa on mitattavaa: pysty pinta joka jatkuu
lattiasta kattoon. Ei Manhattan-oletusta — suunnat luetaan normaalien
kulmahistogrammista, joten vinot seinat kelpaavat.

  1. normaalit harvennetusta pilvesta, pystypinnat |nz| < _VERT_NZ
  2. suuntahistogrammi (mod 180 astetta) -> dominantit seinasuunnat
  3. per suunta: etaisyys normaalin suuntaan -> piikit = seinatasot
  4. per taso: pituussuuntainen klusterointi -> segmentit (aukot katkaisevat)
  5. segmentti kelpaa vain jos se jatkuu pystysuunnassa (ei hylly eika tavara)
  6. paksuus vastakkaisesta pinnasta, muuten oletus

Tulostaa model.json-yhteensopivan seinalistan, jotta `_wall_coverage_nogt.py`
ja `_rohbau_qa.py` mittaavat sen samoilla saannoilla kuin tuotannon mallin.

Kaytto: _wall_from_normals.py <pilvi> <out.json> [floor_mm ceiling_mm]
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

_VOXEL = 25.0
_NORMAL_KNN = 30
_VERT_NZ = 0.35        # |nz| tata pienempi = pystypinta
_DIR_BIN_DEG = 2.0     # suuntahistogrammin bini
_DIR_MIN_FRAC = 0.04   # suunnan oltava tama osuus vahvimmasta suunnasta
_DIR_TOL_DEG = 6.0     # pisteen normaali saa poiketa suunnasta nain paljon
_OFF_BIN = 25.0        # mm — etaisyyshistogrammin bini
_OFF_MIN_FRAC = 0.0     # POISTETTU: "osuus vahvimmasta" hautasi heikot mutta aidot tasot
_PLANE_BAND = 45.0     # mm — kaista tason ymparilla
_GAP_MM = 700.0        # mm — tata pidempi aukko katkaisee segmentin
_MIN_LEN = 900.0       # mm — lyhyempi ei ole seina
_SPAN_FRAC = 0.45      # segmentin z-valin oltava tama osuus kaistasta
_MIN_PTS = 60
_PAIR_MIN, _PAIR_MAX = 80.0, 500.0    # mm — vastakkaisen pinnan etaisyys
_THICK_DEFAULT = 200.0


def _load(path: str) -> np.ndarray:
    p = pathlib.Path(path)
    if p.suffix == ".npy":
        pts = np.load(p).astype(np.float64)
    else:
        import open3d as o3d
        pts = np.asarray(o3d.io.read_point_cloud(str(p)).points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    return pts


def _prepare(pts: np.ndarray):
    import open3d as o3d
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    pc = pc.voxel_down_sample(_VOXEL)
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=_NORMAL_KNN))
    return np.asarray(pc.points), np.asarray(pc.normals)


def _directions(nrm: np.ndarray) -> list[float]:
    """Dominantit seinasuunnat asteina [0,180)."""
    ang = np.degrees(np.arctan2(nrm[:, 1], nrm[:, 0])) % 180.0
    nb = int(180.0 / _DIR_BIN_DEG)
    hist, edges = np.histogram(ang, bins=nb, range=(0.0, 180.0))
    centers = 0.5 * (edges[:-1] + edges[1:])
    # ympyrahistogrammi: huippu myos reunojen yli
    rolled = np.concatenate([hist[-3:], hist, hist[:3]])
    out = []
    for i in range(3, len(rolled) - 3):
        if rolled[i] == rolled[i - 3:i + 4].max() and hist.max() > 0:
            if rolled[i] >= _DIR_MIN_FRAC * hist.max():
                out.append(float(centers[i - 3]))
    return out


def _segments(q: np.ndarray, sel: np.ndarray, deg: float, z_lo: float, z_hi: float):
    """Yhden suunnan seinatasot ja niiden pituussuuntaiset segmentit."""
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy = q[sel][:, :2]
    z = q[sel][:, 2]
    off = xy @ n
    nb = max(int((off.max() - off.min()) / _OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    thr = _OFF_MIN_FRAC * hist.max()
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] >= thr and hist[i] == hist[max(0, i - 2):i + 3].max()]

    need_span = _SPAN_FRAC * (z_hi - z_lo)
    out = []
    for i in peaks:
        c = float(centers[i])
        m = np.abs(off - c) < _PLANE_BAND
        if m.sum() < _MIN_PTS:
            continue
        t = xy[m] @ u
        zz = z[m]
        order = np.argsort(t)
        t, zz = t[order], zz[order]
        cuts = np.flatnonzero(np.diff(t) > _GAP_MM) + 1
        for piece_t, piece_z in zip(np.split(t, cuts), np.split(zz, cuts)):
            if len(piece_t) < _MIN_PTS:
                continue
            length = float(piece_t[-1] - piece_t[0])
            if length < _MIN_LEN:
                continue
            if float(piece_z.max() - piece_z.min()) < need_span:
                continue
            a = n * c + u * float(piece_t[0])
            b = n * c + u * float(piece_t[-1])
            out.append({"offset": c, "dir": deg, "a": a, "b": b,
                        "len": length, "n": int(len(piece_t))})
    return out


_OVERLAP_FRAC = 0.40    # osuus lyhyemmasta: nain paljon paallekkain = sama seina


def _pair_faces(segs: list[dict], deg: float) -> list[dict]:
    """Yhdista seinan KAKSI PINTAA yhdeksi seinaksi.

    Ilman tata jokainen seina tulee malliin kahdesti ja kummankin akseli on
    pinnalla, ei keskella — mittauskaista osuu silloin seinan sisaan tai
    ilmaan. Mitattu Rohbau scene_07004: kahdeksan "seinaa" olivat nelja
    seinaparia, kattavuus 0.052 ja tarkkuus 0.260.
    """
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    for s in segs:
        s["t0"] = float(min(s["a"] @ u, s["b"] @ u))
        s["t1"] = float(max(s["a"] @ u, s["b"] @ u))
    segs = sorted(segs, key=lambda s: -(s["t1"] - s["t0"]))

    used: set[int] = set()
    out: list[dict] = []
    for i, s in enumerate(segs):
        if i in used:
            continue
        best, best_gap = None, None
        for j, o in enumerate(segs):
            if j <= i or j in used:
                continue
            gap = abs(o["offset"] - s["offset"])
            if not (_PAIR_MIN <= gap <= _PAIR_MAX):
                continue
            lo = max(s["t0"], o["t0"])
            hi = min(s["t1"], o["t1"])
            shorter = min(s["t1"] - s["t0"], o["t1"] - o["t0"])
            if shorter <= 0 or (hi - lo) < _OVERLAP_FRAC * shorter:
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = j, gap
        if best is None:
            out.append({**s, "thick": _THICK_DEFAULT})
            continue
        o = segs[best]
        used.add(best)
        mid = 0.5 * (s["offset"] + o["offset"])
        t0 = max(s["t0"], o["t0"])
        t1 = min(s["t1"], o["t1"])
        out.append({"offset": mid, "dir": deg,
                    "a": n * mid + u * t0, "b": n * mid + u * t1,
                    "len": t1 - t0, "n": s["n"] + o["n"], "thick": best_gap})
    return [w for w in out if w["len"] >= _MIN_LEN]


def main(cloud: str, out_json: str, floor: float | None = None,
         ceiling: float | None = None) -> None:
    pts = _load(cloud)
    q, nrm = _prepare(pts)
    if floor is None:
        floor = float(np.percentile(q[:, 2], 2))
        ceiling = float(np.percentile(q[:, 2], 98))
    z_lo, z_hi = floor + 400.0, ceiling - 300.0
    band = (q[:, 2] > z_lo) & (q[:, 2] < z_hi)
    vert = band & (np.abs(nrm[:, 2]) < _VERT_NZ)
    print(f"tyopilvi {len(q):,}  kaista {z_lo:.0f}..{z_hi:.0f}  pystypintoja {int(vert.sum()):,}")

    ang = np.degrees(np.arctan2(nrm[:, 1], nrm[:, 0])) % 180.0
    dirs = _directions(nrm[vert])
    print(f"seinasuuntia {len(dirs)}: {[round(d) for d in dirs]}")

    walls = []
    for deg in dirs:
        d = np.abs((ang - deg + 90.0) % 180.0 - 90.0)
        sel = vert & (d < _DIR_TOL_DEG)
        if sel.sum() < _MIN_PTS:
            continue
        segs = _pair_faces(_segments(q, sel, deg, z_lo, z_hi), deg)
        for s in segs:
            walls.append({
                "id": f"wall_n_{len(walls):03d}",
                "confidence": 1.0,
                "classification": "wall",
                "source": {"method": "normals", "plane_ids": [], "notes": ""},
                "axis": [[float(s["a"][0]), float(s["a"][1])],
                         [float(s["b"][0]), float(s["b"][1])]],
                "height": float(ceiling - floor),
                "thickness": round(float(s["thick"]), 1),
                "z_min": float(floor),
            })
    total = sum(np.linalg.norm(np.array(w["axis"][1][:2]) - np.array(w["axis"][0][:2]))
                for w in walls)
    print(f"seinia {len(walls)}  yhteispituus {total/1000:.1f} m")

    model = {"walls": walls,
             "slabs": [{"id": "slab_000", "confidence": 1.0, "classification": "slab",
                        "source": {"method": "proto", "plane_ids": [], "notes": ""},
                        "slab_type": "floor", "boundary": [], "elevation": float(floor),
                        "thickness": 200.0},
                       {"id": "slab_001", "confidence": 1.0, "classification": "slab",
                        "source": {"method": "proto", "plane_ids": [], "notes": ""},
                        "slab_type": "ceiling", "boundary": [], "elevation": float(ceiling),
                        "thickness": 200.0}],
             "openings": [], "columns": [], "beams": [], "spaces": [], "discarded": [],
             "metadata": {"source": "wall_from_normals prototype"}}
    pathlib.Path(out_json).write_text(json.dumps(model), encoding="utf-8")
    print("kirjoitettu", out_json)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], float(a[2]) if len(a) > 2 else None,
         float(a[3]) if len(a) > 3 else None)

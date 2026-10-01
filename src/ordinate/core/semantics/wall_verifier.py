"""Opittu seinätarkistin: onko ehdokasseinä seinä vai palkki-, pilari- tai porraslinja.

Geometriset portit eivät erota näitä: palkkilinjan alla on pilaririvi joka
täyttää vyötärön, ja portaan pinta on yhtä tasomainen kuin seinän. Mitattu
Rohbau3D:llä (`data/_cand_features.py`, `data/_cand_train.py`): 1116 ehdokasta
93 scenestä, joista 279 ei ole seinää; tarkistin hylkää kynnyksellä 0.5
tyomaa kerrallaan arvioituna valtaosan niistä ja vain harvan seinän.

Malli on satunnaismetsä, joka viedään puina JSONiin
(`scripts/export_wall_verifier.py`), joten ajo ei tarvitse scikit-learnia.
Piirteet lasketaan vain pilvestä — ground truth antaa koulutuksessa tuomion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

NB = 10
FEATURES = (["L", "thick", "npts_rel", "dens_rel", "mad", "horiz", "cont_lo", "cont_mid", "cont_hi",
             "side_free", "zspan", "top_ratio", "horiz_hi", "cross", "par_near", "in_ref"]
            + [f"vp{i}" for i in range(NB)])
_MODEL_FILENAME = "wall_verifier.json"
_VOXEL = 25.0
_KNN = 24


def _seg(w):
    ax = w["axis"] if isinstance(w, dict) else w.axis
    return np.asarray(ax[0], float)[:2], np.asarray(ax[-1], float)[:2]


def _thick(w) -> float:
    return float(w["thickness"] if isinstance(w, dict) else w.thickness)


def _cont(t, L, sel, cell=250.0) -> float:
    n = max(1, int(L / cell))
    if not sel.any():
        return 0.0
    ci = np.clip((t[sel] / L * n).astype(int), 0, n - 1)
    return float(len(np.unique(ci))) / n


def _topo(w, others) -> tuple[float, float]:
    a, b = _seg(w)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    cross, par = 0, 2000.0
    for v in others:
        c, d = _seg(v)
        Lv = float(np.linalg.norm(d - c))
        if Lv < 800:
            continue
        uv = (d - c) / Lv
        if abs(u @ uv) > 0.97:
            ta, tb = (c - a) @ u, (d - a) @ u
            if max(ta, tb) > 0 and min(ta, tb) < L:
                par = min(par, abs(((c + d) / 2 - a) @ n))
            continue
        den = u[0] * uv[1] - u[1] * uv[0]
        if abs(den) < 1e-9:
            continue
        r = c - a
        s_ = (r[0] * uv[1] - r[1] * uv[0]) / den
        t_ = (r[0] * u[1] - r[1] * u[0]) / den
        if 500 < s_ < L - 500 and 500 < t_ < Lv - 500:
            cross += 1
    return float(cross), float(par)


def _one(w, q, nz, fz, cz) -> tuple[dict, np.ndarray]:
    a, b = _seg(w)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    d = q[:, :2] - a
    t, p = d @ u, d @ n
    half = _thick(w) / 2.0
    inside = (t > 0) & (t < L)
    face = inside & (np.abs(np.abs(p) - half) < 80)
    H = max(cz - fz, 1000.0)
    zr = (q[:, 2] - fz) / H
    fz_ = zr[face]
    vp, _ = np.histogram(fz_, bins=NB, range=(0, 1))
    vp = vp / max(vp.sum(), 1)
    pf = p[face]
    mad = float(np.median(np.abs(np.abs(pf) - np.median(np.abs(pf))))) if len(pf) else 999.0
    horiz = float((nz[face] > 0.7).mean()) if face.any() else 0.0
    lo = face & (zr > 0.05) & (zr < 0.35)
    mid = face & (zr > 0.35) & (zr < 0.65)
    hi = face & (zr > 0.65) & (zr < 0.95)
    side = inside & (np.abs(p) > half + 300) & (np.abs(p) < half + 1200) & (zr > 0.3) & (zr < 0.7)
    zspan = float(np.percentile(fz_, 95) - np.percentile(fz_, 5)) if face.sum() > 20 else 0.0
    top = vp[7:].sum() / 0.3
    waist = vp[2:6].sum() / 0.4
    hh = face & (zr > 0.6)
    f = dict(L=L, thick=_thick(w), npts=int(face.sum()), dens=face.sum() / (L / 1000.0), mad=mad,
             horiz=horiz, cont_lo=_cont(t, L, lo), cont_mid=_cont(t, L, mid), cont_hi=_cont(t, L, hi),
             side_free=1.0 - _cont(t, L, side, 500.0), zspan=zspan,
             top_ratio=float(top / max(waist, 1e-3)),
             horiz_hi=float((nz[hh] > 0.7).mean()) if hh.any() else 0.0,
             **{f"vp{i}": float(vp[i]) for i in range(NB)})
    return f, face


def prepare(points: np.ndarray, fz: float, cz: float):
    """Työpilvi piirteille: 25 mm vokselit + normaalien pystykomponentti."""
    import open3d as o3d  # noqa: PLC0415

    pc = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64)))
    pc = pc.voxel_down_sample(_VOXEL)
    pc.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=_KNN))
    q = np.asarray(pc.points)
    nz = np.abs(np.asarray(pc.normals)[:, 2])
    keep = (q[:, 2] > fz - 200) & (q[:, 2] < cz + 200)
    return q[keep], nz[keep]


def features(cands, ref_walls, q, nz, fz, cz, in_ref) -> tuple[np.ndarray, list]:
    """Piirrematriisi ehdokkaille. Palauttaa myös kunkin ehdokkaan face-maskin."""
    rows, faces = [], []
    for w, r in zip(cands, in_ref):
        f, face = _one(w, q, nz, fz, cz)
        f["cross"], f["par_near"] = _topo(w, [x for x in ref_walls if x is not w])
        f["in_ref"] = float(r)
        rows.append(f)
        faces.append(face)
    if not rows:
        return np.zeros((0, len(FEATURES))), faces
    med_n = float(np.median([f["npts"] for f in rows])) or 1.0
    med_d = float(np.median([f["dens"] for f in rows])) or 1.0
    for f in rows:
        f["npts_rel"] = f["npts"] / med_n
        f["dens_rel"] = f["dens"] / med_d
    return np.array([[float(f[k]) for k in FEATURES] for f in rows]), faces


def _model_path() -> Path | None:
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "models" / _MODEL_FILENAME  # type: ignore[attr-defined]
        return p if p.exists() else None
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            p = candidate / "models" / _MODEL_FILENAME
            return p if p.exists() else None
    return None


_CACHE: dict = {}


def load(path: Path | None = None):
    path = path or _model_path()
    if path is None:
        return None
    key = str(path)
    if key not in _CACHE:
        m = json.loads(Path(path).read_text(encoding="utf-8"))
        if list(m["features"]) != FEATURES:
            raise ValueError("wall_verifier: piirrelista ei vastaa mallia")
        _CACHE[key] = [{k: np.asarray(v) for k, v in t.items()} for t in m["trees"]]
    return _CACHE[key]


def predict(trees, X: np.ndarray) -> np.ndarray:
    """Seinän todennäköisyys: puiden lehtiarvojen keskiarvo."""
    out = np.zeros(len(X))
    for t in trees:
        left, right, feat, thr, val = t["left"], t["right"], t["feature"], t["threshold"], t["value"]
        node = np.zeros(len(X), dtype=np.int64)
        active = left[node] >= 0
        while active.any():
            idx = np.flatnonzero(active)
            nd = node[idx]
            go_left = X[idx, feat[nd]] <= thr[nd]
            node[idx] = np.where(go_left, left[nd], right[nd])
            active = left[node] >= 0
        out += val[node]
    return out / max(len(trees), 1)

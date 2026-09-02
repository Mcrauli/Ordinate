"""Onko seinan MOLEMPI pinta oikeasti pinta - vai pinta + roina?

Kellarin mallista 148/240 seinaa (65 % pituudesta) on 60-95 mm paksuja. Se luku
on kaksiselitteinen, ja juuri siksi sita EI saa tuomita paksuuden perusteella:

  a) aito kevyt valiseina - 66 / 92 / 120 mm ovat rankaseinan vakiomitat, ja
     koulun kellarin varastokopit ovat juuri sellaisia;
  b) yksipuolisen pinnan artefakti - `_unsupported_thickness_lock` dokumentoi
     ettei kontuurimaskin levinnyt viiva tuota 66-92 mm "paksuutta".

Muoto on sama, asia eri. Kolmas mitattava ero: AITO valiseina nakyy MOLEMMILTA
puolilta koko pituudeltaan, valepari ei. Valeparin toinen "pinta" on putki,
hylly tai naapurikappale, joka kattaa vain palan seinasta.

Mittari on suhde eika taso, joten se ei riipu skannin tiheydesta:

  kasvot_jatkuvuus = niiden 250 mm sarakkeiden osuus seinan pituudesta,
                     joissa on >= 3 pistetta +-10 mm kyseisesta pinnasta

ja seinan tuomio on HEIKOMPI kasvoista: min(A, B).

Kaytto: _face_pair_probe.py <model.json> <pilvi.ply> [nimi]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_SEARCH = 200.0     # mm - kohtisuora hakukaista (sama kuin _TL_SEARCH)
_BIN = 2.0          # mm - histogrammin bini (sama kuin _TL_BIN)
_PEAK_FRAC = 0.25   # sama kuin _TL_PEAK_FRAC
_FACE_TOL = 10.0    # mm - kuinka lahelta pintaa pisteet luetaan
_COL = 250.0        # mm - sarakkeen leveys jatkuvuuteen
_COL_MIN_PTS = 3
_MIN_PTS = 500


def _continuity(s: np.ndarray, length: float) -> float:
    n = max(int(length / _COL), 1)
    idx = np.clip((s / _COL).astype(int), 0, n - 1)
    counts = np.bincount(idx, minlength=n)
    return float((counts >= _COL_MIN_PTS).mean())


def measure(wall: dict, pts: np.ndarray, index) -> tuple | None:
    """(paksuus, jatkuvuus_A, jatkuvuus_B, pituus) tai None jos ei mitattavissa."""
    from scipy.signal import find_peaks

    from scan2bim.core.geometry.xy_index import subset

    ax = wall.get("axis") or []
    if len(ax) < 2:
        return None
    p0 = np.asarray(ax[0], float)[:2]
    p1 = np.asarray(ax[-1], float)[:2]
    length = float(np.linalg.norm(p1 - p0))
    if length < 800.0:
        return None
    u = (p1 - p0) / length
    n = np.array([-u[1], u[0]])
    q, _ = subset(pts, index, p0, u, n, _SEARCH, 0.0, length)
    if len(q) < _MIN_PTS:
        return None
    z_lo = wall["z_min"] + 200.0
    z_hi = wall["z_min"] + wall["height"] - 200.0
    rel = q[:, :2] - p0
    s = rel @ u
    t = rel @ n
    m = (s >= 0.0) & (s <= length) & (np.abs(t) <= _SEARCH) \
        & (q[:, 2] >= z_lo) & (q[:, 2] <= z_hi)
    if int(m.sum()) < _MIN_PTS:
        return None
    s, t = s[m], t[m]
    edges = np.arange(-_SEARCH, _SEARCH + _BIN, _BIN)
    hist, edges = np.histogram(t, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    pks, _ = find_peaks(hist, height=hist.max() * _PEAK_FRAC, distance=int(20.0 / _BIN))
    if len(pks) < 2:
        return None
    top = sorted((int(p) for p in pks), key=lambda p: hist[p], reverse=True)[:2]
    fa, fb = float(centers[top[0]]), float(centers[top[1]])
    ca = _continuity(s[np.abs(t - fa) <= _FACE_TOL], length)
    cb = _continuity(s[np.abs(t - fb) <= _FACE_TOL], length)
    return abs(fa - fb), ca, cb, length


def main(model_json: str, cloud_path: str, name: str = "") -> None:
    import open3d as o3d

    from scan2bim.core.geometry.xy_index import XYIndex

    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points, dtype=np.float64)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    del pc
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    index = XYIndex(pts)

    rows = []
    for w in m["walls"]:
        r = measure(w, pts, index)
        if r is not None:
            rows.append((w["id"], w["thickness"], *r))
    if not rows:
        print(f"{name}: ei mitattavia seinia")
        return

    th = np.array([r[1] for r in rows])
    weak = np.array([min(r[3], r[4]) for r in rows])
    strong = np.array([max(r[3], r[4]) for r in rows])
    L = np.array([r[5] for r in rows])
    print(f"{name or model_json}: mitattu {len(rows)}/{len(m['walls'])} seinaa, "
          f"{L.sum()/1000:.0f} m")
    print(f"  heikompi pinta: mediaani {np.median(weak):.2f}  "
          f"vahvempi {np.median(strong):.2f}")
    for lo, hi in ((0.0, 60.0), (60.0, 100.0), (100.0, 160.0), (160.0, 1e9)):
        sel = (th >= lo) & (th < hi)
        if not sel.any():
            continue
        print(f"  paksuus {lo:5.0f}-{hi if hi < 1e8 else 999:3.0f} mm: {int(sel.sum()):4d} kpl "
              f"{L[sel].sum()/1000:5.0f} m  heikompi pinta med {np.median(weak[sel]):.2f}  "
              f"alle 0.30: {int((weak[sel] < 0.30).sum()):4d} kpl")
    for k in (0.1, 0.2, 0.3, 0.4, 0.5):
        sel = weak < k
        print(f"  heikompi < {k:.1f}: {int(sel.sum()):4d} kpl  {L[sel].sum()/1000:5.0f} m "
              f"({L[sel].sum()/L.sum()*100:4.1f} % mitatusta pituudesta)")


if __name__ == "__main__":
    main(*sys.argv[1:])

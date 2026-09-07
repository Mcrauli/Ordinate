"""Erottaako HYLLYTASOJEN maara aidon seinan hyllykon etupinnasta?

`second_face._gap_has_shelves` mittaa taman jo, mutta vain katvepintahaun
sisalla: se katsoo emaseinan ja ehdokaspinnan VALIA. Sama todiste on olemassa
mille tahansa seinalle — hyllykon etupinnan TAKANA on toistuvia vaakatasoja,
kipsiseinan takana ei.

Kysymys on kaytannon kannalta tarkea: detektorien unioni antaa Rohbaussa
+0.056 instanssikattavuutta mutta tuo liiketilaan 30 valeseinaa, ja tulva on
kokonaan `normals`ista. Jos tasomittari erottaa ne, normals voi paasta
unioniin ilman etta liiketila hajoaa.

Mittaa vain — ei muuta mitaan. Tulostaa jokaiselle mallin seinalle tasojen
maaran molemmilta puolilta ja vertaa GT:hen siella missa se on.

Kaytto: _shelf_levels_probe.py <model.json> <pilvi.ply> [gt.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from scan2bim.core.semantics import second_face as SF  # noqa: E402

_REACH_LO = 100.0     # mm — aloita nain kaukana seinan pinnasta
_REACH_HI = 1200.0    # mm — seuraa nain kauas sivulle (= _DECK_REACH)
_MIN_PTS = 40


def _levels(pts, w) -> tuple[int, int]:
    """Vaakatasojen maara seinan kummallakin puolella."""
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][1], float)[:2]
    L = float(np.linalg.norm(b - a))
    if L < 500.0:
        return -1, -1
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    d = pts[:, :2] - a
    t = d @ u
    perp = d @ n
    z = pts[:, 2]
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    zlo, zhi = z0 + 300.0, z0 + h - 300.0
    half = 0.5 * float(w.get("thickness") or 200.0)
    out = []
    for sign in (+1.0, -1.0):
        m = ((t >= 0) & (t <= L) & (z > zlo) & (z < zhi)
             & (sign * perp > half + _REACH_LO) & (sign * perp < half + _REACH_HI))
        if int(m.sum()) < _MIN_PTS:
            out.append(0)
            continue
        nbins = max(10, int((zhi - zlo) / SF._SHELF_BIN))
        hist, edges = np.histogram(z[m], bins=nbins, range=(zlo, zhi))
        peaks = np.flatnonzero(hist >= SF._SHELF_PEAK_REL * hist.mean())
        if len(peaks) == 0:
            out.append(0)
            continue
        out.append(1 + int((np.diff(edges[peaks]) > SF._SHELF_SEP).sum()))
    return out[0], out[1]


def main(model_json: str, cloud: str, gt_json: str | None = None) -> None:
    import open3d as o3d
    W = json.loads(Path(model_json).read_text(encoding="utf-8"))["walls"]
    pts = np.asarray(o3d.io.read_point_cloud(cloud).points)
    if len(pts) and float(np.ptp(pts[:, 0])) < 500.0:
        pts = pts * 1000.0
    gt = None
    if gt_json and Path(gt_json).exists():
        g = json.loads(Path(gt_json).read_text(encoding="utf-8"))
        gt = [(np.asarray(w["axis"][0], float)[:2], np.asarray(w["axis"][1], float)[:2])
              for w in g["walls"]]

    def is_gt(w) -> str:
        if gt is None:
            return "?"
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][1], float)[:2]
        c = 0.5 * (a + b)
        for g0, g1 in gt:
            L = np.linalg.norm(g1 - g0)
            if L < 1:
                continue
            u = (g1 - g0) / L
            t = float(np.clip((c - g0) @ u, 0, L))
            if float(np.linalg.norm(c - (g0 + t * u))) < 600.0:
                return "GT"
        return "VALE"

    print(f"{'seina':16s} {'pituus':>7s} {'lahde':12s} {'tasot +':>8s} {'tasot -':>8s} "
          f"{'max':>4s}  {'GT'}")
    rows = []
    for w in W:
        p, m = _levels(pts, w)
        a = np.asarray(w["axis"][0], float)[:2]
        b = np.asarray(w["axis"][1], float)[:2]
        L = float(np.linalg.norm(b - a)) / 1000.0
        tag = is_gt(w)
        rows.append((tag, max(p, m)))
        print(f"{w['id'][:16]:16s} {L:6.1f} m {(w.get('source') or {}).get('method',''):12s} "
              f"{p:8d} {m:8d} {max(p,m):4d}  {tag}")
    if gt is not None:
        for tag in ("GT", "VALE"):
            v = [r[1] for r in rows if r[0] == tag and r[1] >= 0]
            if v:
                print(f"\n{tag:5s} n={len(v):3d}  tasot mediaani {np.median(v):.1f}  "
                      f"kvantiilit {np.percentile(v,[10,50,90]).round(1).tolist()}")


if __name__ == "__main__":
    main(*sys.argv[1:])

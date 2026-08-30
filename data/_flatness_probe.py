"""Erottaako kaistan TASOMAISUUS aidon seinapinnan putkimetsasta?

47 % kellarin seinapituudesta on seinamaisen todisteen ulkopuolella, mutta
Rohbaun aidoilla katvepintaseinilla luku on 24 % — seinamaisyys aliarvioi
korkeassa hallissa, joten pelkka "ei todistetta" ei kelpaa leikkausperusteeksi.

Aito seinapinta on TASO: kaistan pisteiden kohtisuora hajonta on muutamia
millimetreja. Putki, kanava ja kaapeli tayttavat kaistan tasaisesti, jolloin
hajonta on kymmenia millimetreja. Hajonta on mitta pinnasta itsestaan eika
riipu keilaustiheydesta.

Mitataan sarakkeittain (500 mm) seinan pituudelta: kuinka suuri osa
sarakkeista on TASOMAISIA, ja miten se jakautuu aineistojen valilla.

Kaytto: _flatness_probe.py <model.json> <pilvi.ply> [nimi] [voxel_mm]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scan2bim.core.geometry.xy_index import XYIndex, subset  # noqa: E402

_COL = 500.0        # mm — sarake pituussuunnassa
_BAND = 120.0       # mm — kaista pinnan ymparilla
_MIN_PTS = 30       # sarakkeessa oltava nain monta pistetta jotta hajonta kertoo
_FLAT_MM = 20.0     # mm — MAD tata pienempi = taso (sama raja kuin QA:n fiktiokaista)


def main(model_json: str, cloud_path: str, name: str = "", voxel: str = "10",
         out_json: str = "") -> None:
    import open3d as o3d

    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    del pc
    if float(voxel) > 0:
        p2 = o3d.geometry.PointCloud()
        p2.points = o3d.utility.Vector3dVector(pts)
        pts = np.asarray(p2.voxel_down_sample(float(voxel)).points)
        del p2
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"),
             default=float(np.percentile(pts[:, 2], 1)))
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"),
             default=float(np.percentile(pts[:, 2], 99)))
    lo, hi = zf + 0.25 * (zc - zf), zf + 0.75 * (zc - zf)
    pts = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]
    idx = XYIndex(pts)

    tot_cols = flat_cols = 0
    rows = []
    for w in m["walls"]:
        ax = w.get("axis") or []
        if len(ax) < 2:
            continue
        p0 = np.asarray(ax[0], float)[:2]
        p1 = np.asarray(ax[-1], float)[:2]
        L = float(np.linalg.norm(p1 - p0))
        if L < 2000.0:
            continue
        u = (p1 - p0) / L
        n = np.array([-u[1], u[0]])
        half = float(w["thickness"]) / 2.0
        near, _ = subset(pts, idx, p0, u, n, half + _BAND, 0.0, L)
        if not len(near):
            continue
        d = near[:, :2] - p0
        s, t = d @ u, d @ n
        ncol = max(int(L / _COL), 1)
        col = np.clip((s / _COL).astype(int), 0, ncol - 1)
        mads = []
        for c in range(ncol):
            sel = col == c
            if int(sel.sum()) < _MIN_PTS:
                continue
            tc = t[sel]
            b = min(_BAND, max(half, 20.0))
            for side in (-half, half):
                band = tc[np.abs(tc - side) < b]
                if len(band) < _MIN_PTS:
                    continue
                mads.append(float(np.median(np.abs(band - np.median(band)))))
                break
        if mads:
            rows.append((w["id"], L, mads))

    if not rows:
        print(f"{name}: ei mitattavia")
        return
    allm = np.concatenate([np.asarray(r[2]) for r in rows])
    ref = float(np.percentile(allm, 10))     # mallin OMA kohinapohja
    out = {}
    for wid, L, mads in rows:
        m_ = np.asarray(mads)
        out[wid] = {"L": round(L, 1),
                    "abs": float((m_ < _FLAT_MM).mean()),
                    "rel": float((m_ < max(3.0 * ref, 6.0)).mean()),
                    "mad_med": float(np.median(m_))}
    fa = np.array([v["abs"] for v in out.values()])
    fr = np.array([v["rel"] for v in out.values()])
    print(f"{name or model_json:14s} n {len(rows):4d}  kohinapohja {ref:5.1f} mm  "
          f"MAD med {float(np.median(allm)):5.1f} mm")
    for tag, v in (("kiintea 20mm", fa), (f"suhteellinen 3x", fr)):
        print(f"    {tag:16s} min {v.min():.2f} p10 {np.percentile(v,10):.2f} "
              f"med {np.median(v):.2f}  alle 0.30: {float((v<0.30).mean()):.2f}")
    if out_json:
        Path(out_json).write_text(json.dumps(out), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:])

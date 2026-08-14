"""Erottaako PYSTYPROFIILI palkille tehdyn valeseinän aidosta seinästä?

Seinä on lattiasta kattoon; palkki on kaista katon alla. `Wall.support` kertoo
vain KUINKA PALJON pintaa on keilattu, ei MISSÄ korkeudella. Tämä mittaa
tuettujen z-rivien osuuden ja niiden korkeusvälin, ja tulostaa ne GT-luokan
rinnalle (Rohbau3D per-piste-GT).

Ajo: .venv/Scripts/python.exe data/_vprofile_probe.py [model.json]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _evidence_gt import _REG, _STRUCT, gt_purity  # noqa: E402

SCENE = Path("data/_rohbau/site_07/scene_07000")
BAND = 80.0
ROW = 200.0       # mm — z-rivin korkeus
MIN_ROW_PTS = 30  # pistettä jotta rivi lasketaan tuetuksi


def vprofile(w, pts_all):
    """(tuettujen rivien osuus, alin, ylin tuettu korkeus suhteessa seinään)."""
    p0 = np.array(w["axis"][0], float)
    p1 = np.array(w["axis"][1], float)
    L = float(np.linalg.norm(p1 - p0))
    if L < 1.0:
        return None
    u = (p1 - p0) / L
    n = np.array([-u[1], u[0]])
    h = float(w["height"])
    z0 = float(w.get("z_min", 0.0))
    half = float(w["thickness"]) / 2.0

    rel = pts_all[:, :2] - p0
    t = rel @ u
    perp = rel @ n
    z = pts_all[:, 2]
    near = ((t > 0) & (t < L) & (np.abs(perp) < half + 3 * BAND)
            & (z > z0) & (z < z0 + h))
    if near.sum() < 200:
        return None
    perp_n, z_n = perp[near], z[near]

    face = np.abs(np.abs(perp_n) - half) < BAND
    if face.sum() < 100:
        return None
    side = perp_n[face] > 0
    dom = perp_n[face][side] if side.sum() >= (~side).sum() else perp_n[face][~side]
    med = float(np.median(dom))
    on = np.abs(perp_n - med) < BAND
    if on.sum() < 100:
        return None

    nrows = max(1, int(h / ROW))
    ri = np.clip(((z_n[on] - z0) / h * nrows).astype(int), 0, nrows - 1)
    cnt = np.bincount(ri, minlength=nrows)
    occ = cnt >= MIN_ROW_PTS
    idx = np.flatnonzero(occ)
    v_frac = occ.mean()
    v_lo = idx[0] / nrows if len(idx) else 0.0
    v_hi = (idx[-1] + 1) / nrows if len(idx) else 0.0

    # PITUUSSUUNTAINEN jatkuvuus VYÖTÄRÖLLÄ (30–70 % korkeudesta): aito seinä on
    # yhtenäinen, palkkilinja on pilareita 8 m välein → reikiä.
    t_on = t[near][on]
    zr = (z_n[on] - z0) / h
    waist = (zr > 0.30) & (zr < 0.70)
    ncol = max(1, int(L / 500.0))          # 500 mm sarake
    if waist.sum() < 50:
        return v_frac, v_lo, v_hi, 0.0
    ci = np.clip((t_on[waist] / L * ncol).astype(int), 0, ncol - 1)
    ccnt = np.bincount(ci, minlength=ncol)
    return v_frac, v_lo, v_hi, float((ccnt >= 5).mean())


def main() -> None:
    import json
    mj = sys.argv[1] if len(sys.argv) > 1 else \
        "data/output/_rohbau_site_07_scene_07000/floor_00/model.json"
    m = json.loads(Path(mj).read_text(encoding="utf-8"))
    P = np.load(SCENE / "coord.npy").astype(np.float64)
    C = np.load(SCENE / "class.npy").ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0

    zf = min((s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor"), default=0.0)
    zc = max((s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling"), default=zf + 2700)
    band = (P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)
    xy, cls = P[band][:, :2], C[band]
    struct_ids = {k for k, v in _REG.items() if v in _STRUCT}

    rows = []
    for w in m["walls"]:
        pure, k, top = gt_purity(w, xy, cls, struct_ids)
        vp = vprofile(w, P)
        rows.append((pure, k, top, w["id"], w["source"]["method"], vp,
                     float(np.linalg.norm(np.array(w["axis"][1]) - np.array(w["axis"][0])))))
    rows.sort()

    print(f"{'id':14s} {'GT':>5s} {'luokka':10s} {'menet':10s} {'L':>7s} "
          f"{'RIVIT':>6s} {'alaraja':>8s} {'ylaraja':>8s} {'VYOTARO':>8s}")
    for pure, k, top, wid, meth, vp, L in rows:
        if vp is None:
            print(f"{wid:14s} {pure:5.2f} {top:10s} {meth:10s} {L/1000:6.1f}m   (ei mittausta)")
            continue
        frac, lo, hi, waist = vp
        print(f"{wid:14s} {pure:5.2f} {top:10s} {meth:10s} {L/1000:6.1f}m "
              f"{frac:6.2f} {lo:8.2f} {hi:8.2f} {waist:8.2f}")

    good = [r for r in rows if r[0] >= 0.80 and r[5] is not None]
    bad = [r for r in rows if r[0] < 0.50 and r[5] is not None]
    print(f"\nGT-hyvia {len(good)}, GT-huonoja {len(bad)}")
    for i, name in ((0, "tuettujen rivien osuus"), (3, "VYOTARON JATKUVUUS")):
        for lab, grp in (("HYVA", good), ("HUONO", bad)):
            v = sorted(r[5][i] for r in grp)
            if v:
                print(f"  {name:24s} {lab:5s} n={len(v):2d} min={v[0]:5.2f} "
                      f"med={v[len(v)//2]:5.2f} max={v[-1]:5.2f}")
        print()


if __name__ == "__main__":
    main()

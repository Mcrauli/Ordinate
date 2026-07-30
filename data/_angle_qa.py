"""Kulmajaannos per seina: paljonko mallin akseli on kierossa OMAAN
pistepintaansa nahden, ja mita se tarkoittaa millimetreina seinan paassa.

VAROITUS — TAMA EI OLE TARKKUUSMITTARI. Kontrolliajo v0.8.8-mallilla osoitti
ettei tama erottele: se antoi vanhalle (huonommalle) mallille samat pienet luvut
(mediaani 0.13 deg, max 24 mm) kuin korjatulle. Syy: mittari lukee mita tahansa
pisteita +-45 mm kaistasta mallipinnan ymparilta, myos naapuriseinan tai
kalusteen pintaa, ja PCA antaa silloin VAARAN pinnan suunnan. Se ei myoskaan nae
lateraalisiirtymaa lainkaan.

Sijaintitarkkuus mitataan `_tol_heatmap.py`:lla raakapilvea vasten (sarake
pinta.mit = mallipinnan virhe pistepinnan mediaanista). Kayta tata vain karkeaan
kulmaseulontaan ja validoi aina kontrolliajolla vanhaa mallia vasten.

Menetelma: seinan kaistan pisteet -> kummankin pinnan pisteet erikseen
(lateraali lahella +-t/2) -> kumpaankin pintaan PCA-suunta -> keskilinjan
suunta pintojen suuntien keskiarvona (yhden pinnan sovitus kiertaisi akselin
sen pinnan mukaan, ks. AGENTS.md fine_rotate-varoitus).

Kaytto: _angle_qa.py <model.json> <ply|dir> [nimi]
"""
import json, sys, glob, pathlib
import numpy as np

from scan2bim.core.geometry.loader import load_point_cloud

_TOL = 45.0        # mm — pinnan kaista
_MIN_PTS = 400
_MIN_LEN = 1200.0  # mm — lyhyesta ei saa luotettavaa suuntaa


def _load_pts(src: str) -> np.ndarray:
    p = pathlib.Path(src)
    if p.is_dir():
        files = sorted(glob.glob(str(p / "scan_*.ply"))) or sorted(glob.glob(str(p / "*.ply")))
        return np.vstack([np.asarray(load_point_cloud(pathlib.Path(f)).points) for f in files])
    return np.asarray(load_point_cloud(p).points)


def _pca_angle(xy: np.ndarray) -> float | None:
    if len(xy) < _MIN_PTS:
        return None
    c = xy - xy.mean(axis=0)
    w, v = np.linalg.eigh(c.T @ c)
    d = v[:, int(np.argmax(w))]
    return float(np.arctan2(d[1], d[0]))


def run(mj: str, src: str, name: str) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    zf = next(s["elevation"] for s in m["slabs"] if s["slab_type"] == "floor")
    zc = next(s["elevation"] for s in m["slabs"] if s["slab_type"] == "ceiling")
    P = _load_pts(src)
    band = P[(P[:, 2] > zf + 400) & (P[:, 2] < zc - 300)]
    xy = band[:, :2]

    print(f"\n=== {name}   (kaistan pisteita {len(xy)})")
    print(f"{'wall':13s} {'menet':9s} {'L':>5s} {'t':>4s} | {'dkulma':>7s} {'paavirhe':>9s} pinnat")
    rows = []
    for w in sorted(m["walls"], key=lambda w: -w["thickness"]):
        a = np.array(w["axis"][0], float); b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < _MIN_LEN:
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        d = xy - a; s = d @ u; t = d @ n
        base = (s > 100) & (s < L - 100)
        angs, used = [], []
        for sign in (+1.0, -1.0):
            sel = base & (np.abs(t - sign * w["thickness"] / 2.0) < _TOL)
            ang = _pca_angle(xy[sel])
            if ang is not None:
                angs.append(ang)
                used.append("+" if sign > 0 else "-")
        if not angs:
            print(f"{w['id']:13s} {w['source']['method']:9s} {L:5.0f} {w['thickness']:4.0f} | "
                  f"{'-':>7s} {'-':>9s} (ei pintaa)")
            continue
        axis_ang = float(np.arctan2(u[1], u[0]))
        # kulmaero [-90,90)
        diffs = [((ang - axis_ang + np.pi / 2) % np.pi) - np.pi / 2 for ang in angs]
        dang = float(np.mean(diffs))
        end_err = abs(np.tan(dang)) * L / 2.0     # paan lateraalivirhe keskelta kierrettaessa
        rows.append((abs(np.degrees(dang)), end_err, w["id"]))
        flag = "  <== " if end_err > 60.0 else ""
        print(f"{w['id']:13s} {w['source']['method']:9s} {L:5.0f} {w['thickness']:4.0f} | "
              f"{np.degrees(dang):+6.2f}° {end_err:8.0f}mm  {''.join(used)}{flag}")
    if rows:
        errs = np.array([r[1] for r in rows])
        degs = np.array([r[0] for r in rows])
        print(f"  YHTEENVETO n={len(rows)}  |dkulma| mediaani={np.median(degs):.2f}° "
              f"max={degs.max():.2f}°  paavirhe mediaani={np.median(errs):.0f}mm "
              f"max={errs.max():.0f}mm  yli60mm={int((errs > 60).sum())}")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else sys.argv[1])

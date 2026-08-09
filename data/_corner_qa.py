"""KULMAMITTARI (endpoint/corner accuracy, +-1.5mm tavoite).

Päätepistevirhettä EI voi lukea raakapisteiden ääripäistä — naapuriseinä jatkaa
linjaa. Todellinen kulma = kahden kohtisuoran seinän pistepilvestä SOVITETTUJEN
linjojen leikkaus.

Per kohtisuora seinäpari joka kohtaa mallissa:
  1. Hae ground-truth kulma pilvestä:
       - sovita kummankin seinän KESKILINJA (axis) raakapisteistä _qa_band.ply:stä
         (kaksipuolinen harja → robusti total-least-squares -linja)
       - leikkaa kaksi sovitettua linjaa → ground-truth-kulma
  2. Vertaa mallin kulmaan (mallin kahden seinäakselin leikkaus).
  3. Raportoi kulmavirhe: mediaani, %<1.5mm, %<5mm, n.

Lisäksi vertailupohjaksi: jokaisen sovitetun keskilinjan jäännös (kuinka hyvin
linja istuu pisteisiin) — kertoo fyysisen rajan.

Aja:  PYTHONPATH=src .venv/Scripts/python data/_corner_qa.py
Tuottaa myös data/_corner_qa.json (vision-työkalua varten).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import open3d as o3d
from _paths import REPO  # portable dev-tool paths

ROOT_MAIN = Path(str(REPO))
MODEL = ROOT_MAIN / "data" / "output" / "_contour_ifc" / "floor_00" / "model.json"
BAND = ROOT_MAIN / "data" / "_qa_band.ply"
OUT_JSON = ROOT_MAIN / "data" / "_corner_qa.json"

PERP_COS_MAX = 0.30      # |cos| < tämä → kohtisuorat (n. >72.5 astetta)
PERP_HALF = 180.0        # mm — kohtisuora hakukaista pinnan ympärillä
CORNER_REACH = 1400.0    # mm — kulman lähistö along-suunnassa josta pinta sovitetaan
FACE_TOL = 18.0          # mm — piste kuuluu pintaharjalle jos näin lähellä huippua
MIN_FACE_PTS = 120       # min pisteitä luotettavaan pintalinjasovitukseen
SEG_TOL = 400.0          # mm — leikkaus saa olla näin paljon segmentin ulkopuolella ja silti "kohtaava"


def _fit_line_tls_dir(pts: np.ndarray, fixed_dir: np.ndarray):
    """TLS-linja, suunta lukittu fixed_dir:iin (kohtisuora jäännös). (piste, rms)."""
    c = pts.mean(axis=0)
    nrm = np.array([-fixed_dir[1], fixed_dir[0]])
    perp = (pts - c) @ nrm
    rms = float(np.sqrt(np.mean(perp ** 2)))
    return c, rms


def _line_intersection(p1, d1, p2, d2):
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
    b = np.array([p2[0] - p1[0], p2[1] - p1[1]])
    if abs(np.linalg.det(A)) < 1e-9:
        return None
    t = np.linalg.solve(A, b)
    return p1 + t[0] * d1


def _fit_wall_centerline_near_corner(xy, a, b, thickness, model_corner,
                                     partner_corner_t, partner_thick):
    """Sovita seinän KESKILINJA pilvestä kulman lähistöltä, kontaminaatiota välttäen.

    1. Rajaa kapealle along-ikkunalle kulman ympärille.
    2. JÄTÄ POIS kulman overlap-vyöhyke (jossa kohtisuoran seinän pisteet ovat):
       |t - tc| < partner_thick/2 + marginaali.
    3. Histogrammi kohtisuorasta etäisyydestä → 1–2 pintaharjaa.
    4. Sovita jokainen harja seinän SUUNTAAN lukittuna (suunta tunnetaan mallista,
       robustimpi kuin vapaa TLS lyhyellä pätkällä) → pinnan offset akselista.
    5. Keskilinja = pintojen keskiarvo-offset; 2-puolinen jos molemmat harjat löytyy.
    """
    ab = b - a
    L = np.linalg.norm(ab)
    if L < 1.0:
        return None
    u = ab / L
    n = np.array([-u[1], u[0]])
    rel = xy - a
    t = rel @ u
    perp = rel @ n
    tc = float((model_corner - a) @ u)

    half = thickness * 0.5 + PERP_HALF
    excl = partner_thick * 0.5 + 60.0   # overlap-vyöhyke kohtisuoran seinän paksuudelta
    in_win = (np.abs(t - tc) <= CORNER_REACH) & (np.abs(perp) <= half) \
        & (np.abs(t - tc) > excl)
    if in_win.sum() < MIN_FACE_PTS:
        return None
    d_vals = perp[in_win]

    # harjat histogrammista
    edges = np.arange(-half, half + 2.0, 2.0)
    h, _ = np.histogram(d_vals, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    from scipy.signal import find_peaks
    pk, _ = find_peaks(h, height=max(h.max() * 0.25, 8), distance=15)
    if len(pk) == 0:
        return None
    pk = sorted(pk, key=lambda p: h[p], reverse=True)[:2]
    ridge_offsets = sorted(centers[p] for p in pk)

    # sovita kukin harja (suunta lukittu u:hun) → tarkka offset
    face_lines = []
    rms_list = []
    for off in ridge_offsets:
        sel = in_win & (np.abs(perp - off) <= FACE_TOL)
        if sel.sum() < MIN_FACE_PTS // 2:
            continue
        c, rms = _fit_line_tls_dir(xy[sel], u)
        face_off = float((c - a) @ n)   # tarkka kohtisuora offset akselista
        face_lines.append(face_off)
        rms_list.append(rms)
    if not face_lines:
        return None

    two_sided = len(face_lines) >= 2 and (max(face_lines) - min(face_lines)) > 50.0
    center_off = (sum(face_lines) / len(face_lines)) if two_sided else face_lines[0]
    # keskilinjan piste = akselin origo siirretty center_off normaalin suuntaan
    cl_point = a + center_off * n
    return {"c": cl_point, "d": u, "rms": float(np.mean(rms_list)),
            "two_sided": bool(two_sided), "n_faces": len(face_lines)}


def main():
    m = json.loads(MODEL.read_text())
    # välimuisti: 1GB PLY -> xy.npy nopeuttaa toistoja
    xy_cache = ROOT_MAIN / "data" / "_qa_band_xy.npy"
    if xy_cache.exists() and xy_cache.stat().st_mtime >= BAND.stat().st_mtime:
        xy = np.load(xy_cache)
    else:
        band = np.asarray(o3d.io.read_point_cloud(str(BAND)).points)
        xy = np.ascontiguousarray(band[:, :2])
        np.save(xy_cache, xy)
    walls = [w for w in m["walls"]
             if np.linalg.norm(np.array(w["axis"][1]) - np.array(w["axis"][0])) > 1.0]

    arrs = []
    for w in walls:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        ab = b - a
        L = np.linalg.norm(ab)
        u = ab / L
        arrs.append((w, a, b, u, L))

    results = []   # per corner
    n_pairs = 0
    for i in range(len(arrs)):
        wi, ai, bi, ui, Li = arrs[i]
        for j in range(i + 1, len(arrs)):
            wj, aj, bj, uj, Lj = arrs[j]
            if abs(float(np.dot(ui, uj))) > PERP_COS_MAX:
                continue
            # mallin kulma = akselien leikkaus
            mc = _line_intersection(ai, ui, aj, uj)
            if mc is None:
                continue
            ti = float((mc - ai) @ ui)
            tj = float((mc - aj) @ uj)
            # leikkauksen oltava molempien segmenttien lähellä → aito kulma
            if ti < -SEG_TOL or ti > Li + SEG_TOL:
                continue
            if tj < -SEG_TOL or tj > Lj + SEG_TOL:
                continue
            n_pairs += 1
            # ground-truth: sovita molempien keskilinjat pilvestä kulman lähistöltä,
            # jättäen pois kohtisuoran seinän overlap-vyöhykkeen (kontaminaatio).
            fi = _fit_wall_centerline_near_corner(
                xy, ai, bi, wi["thickness"], mc, tj, wj["thickness"])
            fj = _fit_wall_centerline_near_corner(
                xy, aj, bj, wj["thickness"], mc, ti, wi["thickness"])
            if fi is None or fj is None:
                continue
            gt = _line_intersection(fi["c"], fi["d"], fj["c"], fj["d"])
            if gt is None:
                continue
            # sovitettujen linjojen oltava lähellä mallin kulmaa (muuten väärä yhdistys)
            if np.linalg.norm(gt - mc) > 600.0:
                continue
            both_two_sided = fi["two_sided"] and fj["two_sided"]
            err = float(np.linalg.norm(gt - mc))
            results.append({
                "wi": wi["id"], "wj": wj["id"],
                "model_corner": [float(mc[0]), float(mc[1])],
                "gt_corner": [float(gt[0]), float(gt[1])],
                "err_mm": err,
                "both_two_sided": both_two_sided,
                "rms_i": fi["rms"], "rms_j": fj["rms"],
            })

    OUT_JSON.write_text(json.dumps(results, indent=1))

    def stat(name, vals):
        if not vals:
            print(f"  {name}: ei dataa")
            return
        a = np.array(vals)
        print(f"  {name}: mediaani={np.median(a):.2f}mm  keski={a.mean():.2f}mm  "
              f"<1.5mm={100*np.mean(a < 1.5):.0f}%  <5mm={100*np.mean(a < 5):.0f}%  "
              f"<15mm={100*np.mean(a < 15):.0f}%  (n={len(a)})")

    print(f"KULMAMITTARI (model.json vs pilvi-sovitetut keskilinjat)")
    print(f"  kohtisuoria kohtaavia pareja: {n_pairs}   mitattuja kulmia: {len(results)}")
    all_err = [r["err_mm"] for r in results]
    ts_err = [r["err_mm"] for r in results if r["both_two_sided"]]
    stat("KULMAVIRHE (kaikki)", all_err)
    stat("KULMAVIRHE (vain 2-puoliset)", ts_err)
    rms_all = [r["rms_i"] for r in results] + [r["rms_j"] for r in results]
    if rms_all:
        print(f"  linjasovituksen jäännös (fyysinen raja): mediaani={np.median(rms_all):.2f}mm "
              f"keski={np.mean(rms_all):.2f}mm")
    print(f"  -> {OUT_JSON}")


if __name__ == "__main__":
    main()

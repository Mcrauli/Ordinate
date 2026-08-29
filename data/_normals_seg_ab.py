"""A/B: normals-detektorin segmentointi vanhalla ja sarakekohtaisella ehdolla.

Vanha `_segments` katkoo vain pisteiden valimatkasta (700 mm) ja mittaa
pystyulottuvuuden KOKO segmentilta. Kellarissa taso lavistaa kymmenia putkia
ja pilarinkulmia; ne ketjuuntuvat yhdeksi 30 m seinaksi ja yksi korkea putki
riittaa kelpuuttamaan sen pystyehtoon.

Uusi ehto mittaa saman asian PAIKALLISESTI ja SUHTEELLISESTI: sarake (500 mm)
on pintaa kun sen z-peitto on vahintaan puolet saman TASON parhaasta
sarakkeesta. Referenssi on tason oma, joten ehto ei riipu skannin tiheydesta
eika huoneen korkeudesta.

Kaytto: _normals_seg_ab.py <pilvi.ply> [max_pts]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import scan2bim.core.segmentation.wall_normals as WN  # noqa: E402
from scan2bim.core.qa.coverage import wall_coverage  # noqa: E402

_COL = 500.0        # mm — sarake pituussuunnassa
_ZBIN = 100.0       # mm — z-bini peiton mittaukseen
_COL_FRAC = 0.50    # sarakkeen peitto suhteessa tason parhaaseen


def _segments_cols(q, sel, deg, z_lo, z_hi):
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy, z = q[sel][:, :2], q[sel][:, 2]
    off = xy @ n
    nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

    need_span = WN._SPAN_FRAC * (z_hi - z_lo)
    out = []
    for i in peaks:
        c = float(centers[i])
        m = np.abs(off - c) < WN._PLANE_BAND
        if m.sum() < WN._MIN_PTS:
            continue
        t, zz = xy[m] @ u, z[m]
        t0 = float(t.min())
        col = ((t - t0) / _COL).astype(np.int64)
        zb = ((zz - z_lo) / _ZBIN).astype(np.int64)
        n_col = int(col.max()) + 1
        key = col.astype(np.int64) * 100000 + zb
        uk = np.unique(key)
        cov = np.bincount(uk // 100000, minlength=n_col)
        best = int(cov.max())
        if best <= 0:
            continue
        good = cov >= max(_COL_FRAC * best, 1.0)

        # aukot: sallitaan _GAP_MM kuten ennen (oviaukko ei katkaise)
        bridge = int(WN._GAP_MM / _COL)
        runs, start, gap = [], None, 0
        for k in range(n_col + 1):
            g = bool(good[k]) if k < n_col else False
            if g:
                if start is None:
                    start = k
                gap = 0
            elif start is not None:
                gap += 1
                if gap > bridge or k == n_col:
                    runs.append((start, k - gap))
                    start, gap = None, 0
        if start is not None:
            runs.append((start, n_col - gap))

        for c0, c1 in runs:
            length = (c1 - c0) * _COL
            if length < WN._MIN_LEN:
                continue
            sel_pts = (col >= c0) & (col < c1)
            if sel_pts.sum() < WN._MIN_PTS:
                continue
            pz = zz[sel_pts]
            if float(pz.max() - pz.min()) < need_span:
                continue
            ta, tb = t0 + c0 * _COL, t0 + c1 * _COL
            out.append({"offset": c, "a": n * c + u * ta, "b": n * c + u * tb,
                        "n": int(sel_pts.sum())})
    return out


def _segments_scene(q, sel, deg, z_lo, z_hi):
    """Sama, mutta referenssi on SUUNNAN oma p90 eika tason paras.

    Roskataso asettaa itse rimansa matalalle jos referenssi on sen oma paras
    sarake. Suunnan kaikkien tasojen sarakkeista laskettu p90 kertoo miltä
    TAYSIN keilattu pinta tassa rakennuksessa nayttaa.
    """
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy, z = q[sel][:, :2], q[sel][:, 2]
    off = xy @ n
    nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

    planes = []
    allcov = []
    for i in peaks:
        c = float(centers[i])
        m = np.abs(off - c) < WN._PLANE_BAND
        if m.sum() < WN._MIN_PTS:
            continue
        t, zz = xy[m] @ u, z[m]
        t0 = float(t.min())
        col = ((t - t0) / _COL).astype(np.int64)
        zb = ((zz - z_lo) / _ZBIN).astype(np.int64)
        n_col = int(col.max()) + 1
        uk = np.unique(col.astype(np.int64) * 100000 + zb)
        cov = np.bincount(uk // 100000, minlength=n_col)
        planes.append((c, t, zz, t0, col, cov, n_col))
        allcov.append(cov[cov > 0])
    if not planes:
        return []
    ref = float(np.percentile(np.concatenate(allcov), 90))
    need_span = WN._SPAN_FRAC * (z_hi - z_lo)
    bridge = int(WN._GAP_MM / _COL)
    out = []
    for c, t, zz, t0, col, cov, n_col in planes:
        good = cov >= max(_COL_FRAC * ref, 1.0)
        runs, start, gap = [], None, 0
        for k in range(n_col + 1):
            g = bool(good[k]) if k < n_col else False
            if g:
                if start is None:
                    start = k
                gap = 0
            elif start is not None:
                gap += 1
                if gap > bridge or k == n_col:
                    runs.append((start, k - gap))
                    start, gap = None, 0
        if start is not None:
            runs.append((start, n_col - gap))
        for c0, c1 in runs:
            if (c1 - c0) * _COL < WN._MIN_LEN:
                continue
            sp = (col >= c0) & (col < c1)
            if sp.sum() < WN._MIN_PTS:
                continue
            pz = zz[sp]
            if float(pz.max() - pz.min()) < need_span:
                continue
            out.append({"offset": c, "a": n * c + u * (t0 + c0 * _COL),
                        "b": n * c + u * (t0 + c1 * _COL), "n": int(sp.sum())})
    return out


_CTRL_LO, _CTRL_HI = 750.0, 1250.0   # mm — kontrollietaisyys tason sivussa
_MIN_CONTRAST = 1.5


def _segments_contrast(q, sel, deg, z_lo, z_hi):
    """Vanha segmentointi + tason KONTRASTI ymparistoonsa.

    Tason pistemaara ei kerro onko se seina: putkimetsassa jokainen taso
    kerää pisteita. Kertova mitta on suhde samaan mittaan 0.75-1.25 m
    sivussa — aito seina erottuu, putkilinja ei. Suhde on dimensioton eika
    riipu keilaustiheydesta.
    """
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy, z = q[sel][:, :2], q[sel][:, 2]
    off = xy @ n
    nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

    half_w = max(int(WN._PLANE_BAND / WN._OFF_BIN), 1)
    c_lo = int(_CTRL_LO / WN._OFF_BIN)
    c_hi = int(_CTRL_HI / WN._OFF_BIN)

    def window(i):
        a, b = max(i - half_w, 0), min(i + half_w + 1, len(hist))
        return float(hist[a:b].sum())

    need_span = WN._SPAN_FRAC * (z_hi - z_lo)
    out = []
    for i in peaks:
        ctrl = [window(i + d) for d in (c_lo, c_hi, -c_lo, -c_hi)
                if 0 <= i + d < len(hist)]
        if ctrl and (window(i) + 1.0) / (float(np.median(ctrl)) + 1.0) < _MIN_CONTRAST:
            continue
        c = float(centers[i])
        m = np.abs(off - c) < WN._PLANE_BAND
        if m.sum() < WN._MIN_PTS:
            continue
        t, zz = xy[m] @ u, z[m]
        order = np.argsort(t)
        t, zz = t[order], zz[order]
        cuts = np.flatnonzero(np.diff(t) > WN._GAP_MM) + 1
        for pt, pz in zip(np.split(t, cuts), np.split(zz, cuts)):
            if len(pt) < WN._MIN_PTS or float(pt[-1] - pt[0]) < WN._MIN_LEN:
                continue
            if float(pz.max() - pz.min()) < need_span:
                continue
            out.append({"offset": c, "a": n * c + u * float(pt[0]),
                        "b": n * c + u * float(pt[-1]), "n": int(len(pt))})
    return out


def _segments_seg_contrast(q, sel, deg, z_lo, z_hi):
    """Kontrasti mitattuna SEGMENTIN omalta pituudelta, ei koko tasolta.

    Taso ulottuu koko rakennuksen lapi, joten sen kontrasti laimenee. Segmentti
    on se mika mallinnetaan seinaksi, ja sen kohdalla kysymys on tarkka:
    onko TASSA kohdassa enemman pystypintaa kuin metrin sivussa.
    """
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy, z = q[sel][:, :2], q[sel][:, 2]
    off_all = xy @ n
    t_all = xy @ u
    off = off_all
    nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

    need_span = WN._SPAN_FRAC * (z_hi - z_lo)
    out = []
    for i in peaks:
        c = float(centers[i])
        m = np.abs(off - c) < WN._PLANE_BAND
        if m.sum() < WN._MIN_PTS:
            continue
        tt, zz = xy[m] @ u, z[m]
        order = np.argsort(tt)
        tt, zz = tt[order], zz[order]
        cuts = np.flatnonzero(np.diff(tt) > WN._GAP_MM) + 1
        for pt, pz in zip(np.split(tt, cuts), np.split(zz, cuts)):
            if len(pt) < WN._MIN_PTS or float(pt[-1] - pt[0]) < WN._MIN_LEN:
                continue
            if float(pz.max() - pz.min()) < need_span:
                continue
            span = (t_all > pt[0]) & (t_all < pt[-1])
            on = int(len(pt))
            ctrl = []
            for d in (_CTRL_LO, _CTRL_HI, -_CTRL_LO, -_CTRL_HI):
                ctrl.append(int((span & (np.abs(off_all - (c + d))
                                         < WN._PLANE_BAND)).sum()))
            if (on + 1.0) / (float(np.median(ctrl)) + 1.0) < _MIN_CONTRAST:
                continue
            out.append({"offset": c, "a": n * c + u * float(pt[0]),
                        "b": n * c + u * float(pt[-1]), "n": on})
    return out


_WALLISH_XY = None      # asetetaan main():ssa — KAIKKI seinamaiset pisteet


def _segments_wallish_contrast(q, sel, deg, z_lo, z_hi):
    """Kontrasti mitattuna KAIKISTA seinamaisista pisteista, ei vain taman
    suunnan pisteista.

    Suuntasuodatettu kontrolli on aina tyhja (metrin sivussa ei ole samaan
    suuntaan osoittavia normaaleja), joten se ei kerro mitaan. Kysymys on
    onko TASSA kohdassa enemman pystypintaa kuin sen vieressa — mika tahansa
    pystypinta kelpaa kontrolliksi, koska juuri sen olemassaolo tekee paikasta
    tavallisen eika erityisen.
    """
    n = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))])
    u = np.array([-n[1], n[0]])
    xy, z = q[sel][:, :2], q[sel][:, 2]
    off = xy @ n
    nb = max(int((off.max() - off.min()) / WN._OFF_BIN), 4)
    hist, edges = np.histogram(off, bins=nb)
    centers = 0.5 * (edges[:-1] + edges[1:])
    peaks = [i for i in range(1, len(hist) - 1)
             if hist[i] and hist[i] == hist[max(0, i - 2):i + 3].max()]

    W = _WALLISH_XY
    w_off = W @ n if W is not None else None
    w_t = W @ u if W is not None else None

    need_span = WN._SPAN_FRAC * (z_hi - z_lo)
    out = []
    for i in peaks:
        c = float(centers[i])
        m = np.abs(off - c) < WN._PLANE_BAND
        if m.sum() < WN._MIN_PTS:
            continue
        tt, zz = xy[m] @ u, z[m]
        order = np.argsort(tt)
        tt, zz = tt[order], zz[order]
        cuts = np.flatnonzero(np.diff(tt) > WN._GAP_MM) + 1
        for pt, pz in zip(np.split(tt, cuts), np.split(zz, cuts)):
            if len(pt) < WN._MIN_PTS or float(pt[-1] - pt[0]) < WN._MIN_LEN:
                continue
            if float(pz.max() - pz.min()) < need_span:
                continue
            if W is not None:
                span = (w_t > pt[0]) & (w_t < pt[-1])
                on = int((span & (np.abs(w_off - c) < 80.0)).sum())
                ctrl = [int((span & (np.abs(w_off - (c + d)) < 80.0)).sum())
                        for d in (_CTRL_LO, _CTRL_HI, -_CTRL_LO, -_CTRL_HI)]
                if (on + 1.0) / (float(np.median(ctrl)) + 1.0) < _MIN_CONTRAST:
                    continue
            out.append({"offset": c, "a": n * c + u * float(pt[0]),
                        "b": n * c + u * float(pt[-1]), "n": int(len(pt))})
    return out


def main(cloud_path: str, max_pts: str = "3000000") -> None:
    import open3d as o3d
    pc = o3d.io.read_point_cloud(cloud_path)
    pts = np.asarray(pc.points)
    if np.ptp(pts[:, 0]) < 500.0:
        pts = pts * 1000.0
    lim = int(max_pts)
    if len(pts) > lim:
        pts = pts[:: -(-len(pts) // lim)]
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    print(f"pisteita {len(pts):,}")

    global _WALLISH_XY
    from scan2bim.core.qa.coverage import wallish_points
    _fz = float(np.percentile(pts[:, 2], 2)); _cz = float(np.percentile(pts[:, 2], 98))
    _mask, _q = wallish_points(pts, _fz + 400.0, _cz - 300.0)
    _WALLISH_XY = _q[_mask][:, :2]
    print(f"seinamaisia {len(_WALLISH_XY):,}")

    floor = float(np.percentile(pts[:, 2], 2))
    ceiling = float(np.percentile(pts[:, 2], 98))
    orig = WN._segments
    variants = [("vanha", orig, None)]
    for thr in (1.5, 2.0, 3.0, 5.0):
        variants.append((f"kontrasti {thr}", _segments_wallish_contrast, thr))
    for name, fn, thr in variants:
        global _MIN_CONTRAST
        if thr is not None:
            _MIN_CONTRAST = thr
        WN._segments = fn
        m = WN.NormalsWallDetector().detect(pc)
        WN._segments = orig
        length = sum(float(np.linalg.norm(np.array(w.axis[-1]) - np.array(w.axis[0])))
                     for w in m.walls) / 1000.0
        cov = wall_coverage(pts, m.walls, floor, ceiling)
        print(f"{name:10s} seinia {len(m.walls):4d}  pituus {length:7.0f} m  "
              f"kattavuus {cov:.3f}")


if __name__ == "__main__":
    main(*sys.argv[1:])

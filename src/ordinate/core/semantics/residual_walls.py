"""Jäännösseinät: mitä seinämäistä jää detektorin ulkopuolelle.

Histogrammidetektori löytää HALLITSEVAT seinälinjat — mitattu Rohbau3D
scene_07000: neljä seinää, kaikki 27–30 m, ja GT:n 49 seinäinstanssista
mallissa on 24. Kynnys ei ole syy: `_MIN_WALL_LENGTH` 2000 → 1200 ei muuttanut
yhtään lukua, koska lyhyestä seinästä ei synny globaalia piikkiä lainkaan.
Contour-reititys ei auta sekään (instanssikattavuus 0.306 vs histogrammin
0.490) eikä kumpikaan löydä yhtään 1–2 m seinää.

Puuttuvat seinät EIVÄT ole sirontaa: kun mallin seinien lunastamat pisteet
poistetaan, jäännöksessä on 15 suoraa 1.2–5.6 m rakennetta joiden GT-luokka on
92–100 % Wall (`data/_residual_walls.py`). Tämä moduuli tekee niistä seiniä.

Ehdokkaat menevät läpi koko olemassa olevan todistusketjun (dedup, suoristus,
paksuuden tarkennus, tuen mittaus, karsinta, hyllykarsinta, ylivenytyksen
leikkaus) — tämä ei päätä mikä on seinä, se vain tuo ehdokkaan katsottavaksi.
"""
from __future__ import annotations

import numpy as np

from ordinate.schemas.model import ElementSource, Wall

_CELL = 100.0            # mm — jäännöksen ruudukko
_CLAIM_BAND = 80.0       # mm — mallin seinän pinnan ympärillä lunastettu kaista
_CLAIM_END = 200.0       # mm — seinän päiden yli lunastettu jatke
_MIN_LEN = 1000.0        # mm — lyhyempi ei ole seinä vaan pilari/tolppa
_MIN_ASPECT = 4.0        # pituus/leveys
_MAX_WIDTH = 700.0       # mm — leveämpi on kalusteryhmä tai laatan reuna
_MIN_CELLS = 10
_SURF_FRAC = 0.5         # solu on pintaa jos siinä on tämä osuus MEDIAANIsolusta.
                         # Suhteellinen, koska absoluuttinen pistemäärä sitoisi
                         # säännön skannin tiheyteen.
_MIN_VSPAN_MM = 800.0    # mm — pystypinnan vähimmäisulottuvuus. Osuutena kaistasta
                         # tämä oli väärin: 10 m hallissa kaista on 5.6 m ja puolikas
                         # siitä 2.8 m, mutta kaukaisesta seinästä NÄKYY vain 1.8–2.2 m.
                         # Kysymys on 'onko tämä pystypinta vai hyllyn taso', ja siihen
                         # 800 mm yhtenäistä pystyä vastaa fysikaalisesti.
_MIN_VSPAN_FRAC = 0.5    # …matalassa tilassa ei yli puolta kaistasta
_PAIR_MIN, _PAIR_MAX = 60.0, 500.0   # mm — vastakkaisten pintojen väli = paksuus
_PAIR_COS = 0.985                    # cos 10°
_PAIR_OVERLAP = 0.5                  # osuus lyhyemmästä pinnasta
_NEAR_EXISTING = 600.0               # mm — tätä lähempänä samansuuntaista mallin
                                     # seinää oleva ehdokas ON se seinä (sen toinen
                                     # pinta tai liian ohueksi mitattu paksuus), ei
                                     # uusi seinä. Ilman tätä ehdokkaat sulautuivat
                                     # deduplikoinnissa oikeisiin seiniin ja
                                     # LYHENSIVÄT niitä: mitattu Rohbau scene_07000
                                     # pistekattavuus 0.887 → 0.689, 30.3 m seinä
                                     # katkesi 15.4 m:iin.
_NEAR_COS = 0.966                    # cos 15°
_WAIST_HI = 0.65         # kaistan yläraja osuutena huonekorkeudesta
_WAIST_LO_MM = 900.0     # kaistan alaraja lattiasta MILLEINÄ: alaraja on kyse
                         # lattiakrääsästä, ei tilan korkeudesta. Osuutena (0.25)
                         # se nousi 10 m hallissa 2.5 m:iin ja jätti seinäpinnan
                         # alaosan kokonaan pois — mitattu Rohbau scene_07000:
                         # vapaita pisteitä 154 906 kun kaista alkoi 2.5 m:stä.
_WAIST_LO_FRAC = 0.25    # …mutta matalassa tilassa ei yli neljänneskorkeuden
_DEFAULT_THICKNESS = 200.0
_CELL_VSPAN_FRAC = 0.6
_WIDE = object()


def find_residual_walls(walls: list[Wall], cloud, floor_z: float,
                        ceiling_z: float, split_wide: bool = False) -> list[Wall]:
    """Seinäehdokkaat pisteistä joita yksikään mallin seinä ei lunasta.

    `split_wide`: pilko liian leveä komponentti soluihin joiden pisteet
    ulottuvat koko vyötärökaistan läpi. Vain isossa matalassa tilassa: siellä
    seinälinja liimautuu putkisotkuun, mutta korkeassa tilassa hyllyjen päädyt
    ovat yhtä korkeita kuin seinät (mitattu retail_l 13 → 103 seinää).
    """
    from scipy.ndimage import label as _cc_label

    pts = np.asarray(cloud.points, dtype=np.float64)
    height = ceiling_z - floor_z
    if len(pts) < 500 or height < 1500.0:
        return []

    z_lo = floor_z + min(_WAIST_LO_FRAC * height, _WAIST_LO_MM)
    z_hi = floor_z + _WAIST_HI * height
    band = pts[(pts[:, 2] > z_lo) & (pts[:, 2] < z_hi)]
    if len(band) < 500:
        return []

    free = band[~_claimed(band, walls)]
    if len(free) < 200:
        return []

    origin = free[:, :2].min(axis=0)
    ij = np.floor((free[:, :2] - origin) / _CELL).astype(np.int64)
    nx, ny = int(ij[:, 0].max()) + 1, int(ij[:, 1].max()) + 1
    flat = ij[:, 0] * ny + ij[:, 1]
    counts = np.bincount(flat, minlength=nx * ny)
    occupied = counts[counts > 0]
    if not len(occupied):
        return []
    # Suhteellinen pintakynnys: mediaanisolu kertoo tämän skannin tiheyden.
    # Absoluuttinen pistemäärä sitoisi säännön keilaimeen. Kahden pisteen
    # pohja on vain degeneraatiosuoja, ei tiheysmittari.
    need = max(_SURF_FRAC * float(np.median(occupied)), 2.0)
    surf = (counts >= need).reshape(nx, ny)

    labels, ncomp = _cc_label(surf, structure=np.ones((3, 3), dtype=int))
    if ncomp == 0:
        return []
    lab_flat = labels.ravel()
    z_min_w = min((w.z_min for w in walls), default=floor_z)
    h_w = max((w.height for w in walls), default=height)
    th_w = float(np.median([w.thickness for w in walls])) if walls else _DEFAULT_THICKNESS

    vmin = min(_MIN_VSPAN_MM, _MIN_VSPAN_FRAC * (z_hi - z_lo))
    tall = None
    used = np.zeros((nx, ny), dtype=bool)
    out: list = []
    for k in range(1, ncomp + 1):
        comp = labels == k
        face = _component_face(comp, lab_flat == k, flat, free, origin, vmin)
        if face is _WIDE and split_wide:
            if tall is None:
                tall = _tall_cells(free[:, 2], flat, nx * ny,
                                   min(_MIN_VSPAN_MM, _CELL_VSPAN_FRAC * (z_hi - z_lo))).reshape(nx, ny)
            sub, nsub = _cc_label(comp & tall, structure=np.ones((3, 3), dtype=int))
            sub_flat = sub.ravel()
            for j in range(1, nsub + 1):
                f = _component_face(sub == j, sub_flat == j, flat, free, origin, vmin)
                if f is not None and f is not _WIDE:
                    out.append(f)
                    used |= sub == j
        elif face is not None and face is not _WIDE:
            out.append(face)
            used |= comp

    if split_wide and tall is not None:
        out.extend(_line_faces(surf & tall & ~used, free, flat, ny, origin, vmin))

    return _to_walls(_drop_near_existing(_pair_faces(out), walls), h_w, th_w, z_min_w,
                     taken={w.id for w in walls})


_LINE_MIN_CELLS = 15
_LINE_MAX_GAP_CELLS = 6
_LINE_BAND = 150.0


def _line_faces(mask: np.ndarray, free: np.ndarray, flat: np.ndarray, ny: int,
                origin: np.ndarray, vmin: float) -> list:
    """Suorat linjat pystysuuntaisista soluista aukkojen yli.

    Putkien takaa keilattu seinä näkyy pätkinä: yhtenäinen komponentti ei
    koskaan kasva seinän mittaiseksi, mutta viivahaku hyppää aukkojen yli.
    """
    import cv2  # noqa: PLC0415

    img = mask.astype(np.uint8) * 255
    segs = cv2.HoughLinesP(img, 1, np.pi / 360, threshold=10,
                           minLineLength=_LINE_MIN_CELLS, maxLineGap=_LINE_MAX_GAP_CELLS)
    if segs is None:
        return []
    cell_ok = mask.ravel()[flat]
    pts = free[cell_ok]
    taken = np.zeros(len(pts), dtype=bool)
    cands = []
    for a, b, c, d in segs[:, 0, :]:
        p = origin + np.array([b, a], dtype=np.float64) * _CELL + _CELL / 2.0
        q = origin + np.array([d, c], dtype=np.float64) * _CELL + _CELL / 2.0
        cands.append((float(np.linalg.norm(q - p)), p, q))
    out = []
    for L, p, q in sorted(cands, key=lambda t: -t[0]):
        if L < _MIN_LEN:
            continue
        u = (q - p) / L
        n = np.array([-u[1], u[0]])
        rel = pts[:, :2] - p
        t = rel @ u
        sel = (t > -_CELL) & (t < L + _CELL) & (np.abs(rel @ n) < _LINE_BAND)
        if not sel.any() or taken[sel].mean() > 0.5:
            continue
        q3 = pts[sel]
        if float(np.ptp(q3[:, 2])) < vmin:
            continue
        taken |= sel
        cq = np.array([np.median(q3[:, 0]), np.median(q3[:, 1])])
        sq = (q3[:, :2] - cq) @ u
        out.append((cq + u * float(sq.min()), cq + u * float(sq.max()), u, float(np.ptp(sq))))
    return out


def _tall_cells(z: np.ndarray, flat: np.ndarray, ncells: int, need: float) -> np.ndarray:
    """Solut joiden pisteet ulottuvat pystysuunnassa vähintään `need`."""
    order = np.lexsort((z, flat))
    fs = flat[order]
    zs = z[order]
    cells, start, cnt = np.unique(fs, return_index=True, return_counts=True)
    lo = zs[start + np.floor(0.05 * (cnt - 1)).astype(np.int64)]
    hi = zs[start + np.floor(0.95 * (cnt - 1)).astype(np.int64)]
    out = np.zeros(ncells, dtype=bool)
    out[cells] = (hi - lo) >= need
    return out


def _component_face(comp: np.ndarray, cell_sel: np.ndarray, flat: np.ndarray,
                    free: np.ndarray, origin: np.ndarray, vmin: float):
    cx, cy = np.nonzero(comp)
    if len(cx) < _MIN_CELLS:
        return None
    xy = np.column_stack([cx, cy]).astype(np.float64) * _CELL + origin + _CELL / 2.0
    c = xy.mean(axis=0)
    A = xy - c
    _, V = np.linalg.eigh(A.T @ A / len(A))
    u, n = V[:, 1], V[:, 0]
    length = float(np.ptp(A @ u)) + _CELL
    width = float(np.ptp(A @ n)) + _CELL
    if length < _MIN_LEN:
        return None
    if width > _MAX_WIDTH or length / width < _MIN_ASPECT:
        return _WIDE
    q = free[cell_sel[flat]]
    if not len(q):
        return None
    # Pystyulottuvuus: seinä on pinta koko vyötärökaistan läpi, kalusteen
    # yläpinta on ohut viipale.
    if float(np.ptp(q[:, 2])) < vmin:
        return None
    # Pinnan sijainti luetaan PISTEISTÄ, ei solukeskipisteistä: 100 mm solu
    # siirtäisi pintaa puoli solua ulospäin ja parin keskilinja jäisi 50 mm
    # sivuun. Sama estimaattori kuin `_align_faces_to_surface_median`.
    cq = np.array([np.median(q[:, 0]), np.median(q[:, 1])])
    sq = (q[:, :2] - cq) @ u
    return (cq + u * float(sq.min()), cq + u * float(sq.max()), u, float(np.ptp(sq)))


def _drop_near_existing(pairs: list, walls: list[Wall]) -> list:
    """Pudota ehdokkaat jotka ovat olemassa olevan seinän toinen pinta."""
    out = []
    for p0, p1, thickness in pairs:
        a = np.asarray(p0, dtype=float)
        b = np.asarray(p1, dtype=float)
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        dup = False
        for w in walls:
            wa = np.asarray(w.axis[0], dtype=float)
            wb = np.asarray(w.axis[1], dtype=float)
            Lw = float(np.linalg.norm(wb - wa))
            if Lw < 500.0:
                continue
            uw = (wb - wa) / Lw
            if abs(float(u @ uw)) < _NEAR_COS:
                continue
            nw = np.array([-uw[1], uw[0]])
            if max(abs(float((a - wa) @ nw)), abs(float((b - wa) @ nw))) > _NEAR_EXISTING:
                continue
            sa = sorted([float((a - wa) @ uw), float((b - wa) @ uw)])
            if min(sa[1], Lw) - max(sa[0], 0.0) > 0.3 * L:
                dup = True
                break
        if not dup:
            out.append((p0, p1, thickness))
    return out


def _pair_faces(faces: list) -> list:
    """Yhdistä saman seinän kaksi pintaa yhdeksi akseliksi.

    Keilain näkee seinästä kaksi pystypintaa; ilman parittamista molemmista
    tulisi oma seinä 200 mm päähän toisistaan. Pariutuminen antaa myös
    MITATUN paksuuden arvatun sijaan.
    """
    used: set[int] = set()
    out: list = []
    order = sorted(range(len(faces)), key=lambda i: -faces[i][3])
    for i in order:
        if i in used:
            continue
        a0, a1, ua, La = faces[i]
        na = np.array([-ua[1], ua[0]])
        best = None
        for j in order:
            if j == i or j in used:
                continue
            b0, b1, ub, Lb = faces[j]
            if abs(float(ua @ ub)) < _PAIR_COS:
                continue
            gap = abs(float((0.5 * (b0 + b1) - a0) @ na))
            if not (_PAIR_MIN <= gap <= _PAIR_MAX):
                continue
            sa = sorted([0.0, La])
            sb = sorted([float((b0 - a0) @ ua), float((b1 - a0) @ ua)])
            ov = min(sa[1], sb[1]) - max(sa[0], sb[0])
            if ov < _PAIR_OVERLAP * min(La, Lb):
                continue
            if best is None or gap < best[0]:
                best = (gap, j, sb)
        if best is None:
            out.append((a0, a1, None))
            used.add(i)
            continue
        gap, j, sb = best
        used.update({i, j})
        b0, b1, _, _ = faces[j]
        mid = 0.5 * (a0 + 0.5 * (b0 + b1) - na * 0.0)
        shift = na * (float((0.5 * (b0 + b1) - a0) @ na) / 2.0)
        lo = min(0.0, sb[0])
        hi = max(La, sb[1])
        out.append((a0 + ua * lo + shift, a0 + ua * hi + shift, gap))
    return out


def _to_walls(pairs: list, h_w: float, th_w: float, z_min_w: float,
              taken: set[str] | None = None) -> list[Wall]:
    """taken = mallissa jo olevat id:t.

    Putki ajaa jäännöshaun KAHDESTI (ketjun sisällä ja sen jälkeen), ja
    kumpikin numeroi nollasta → kellarin mallissa oli `wall_res_000…008`
    kahteen kertaan. Duplikaatti-id sekoittaa IFC:n, QA:n ja jokaisen
    työkalun joka viittaa seinään id:llä.
    """
    used = set(taken or ())
    walls: list[Wall] = []
    n = 0
    for p0, p1, thickness in pairs:
        if float(np.linalg.norm(np.asarray(p1) - np.asarray(p0))) < _MIN_LEN:
            continue
        while f"wall_res_{n:03d}" in used:
            n += 1
        wid = f"wall_res_{n:03d}"
        used.add(wid)
        walls.append(Wall(
            id=wid,
            confidence=0.5,
            classification="wall",
            source=ElementSource(method="residual"),
            axis=[[round(float(p0[0]), 1), round(float(p0[1]), 1)],
                  [round(float(p1[0]), 1), round(float(p1[1]), 1)]],
            height=float(h_w),
            thickness=float(thickness) if thickness is not None else float(th_w),
            z_min=float(z_min_w),
        ))
    return walls


def _claimed(band: np.ndarray, walls: list[Wall]) -> np.ndarray:
    claimed = np.zeros(len(band), dtype=bool)
    xy = band[:, :2]
    index = None
    if len(band) >= 300_000 and len(walls) >= 3:
        from ordinate.core.geometry.xy_index import XYIndex  # noqa: PLC0415
        index = XYIndex(xy)
    for w in walls:
        a = np.asarray(w.axis[0], dtype=float)
        b = np.asarray(w.axis[1], dtype=float)
        L = float(np.linalg.norm(b - a))
        if L < 500.0:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        r = w.thickness / 2.0 + _CLAIM_BAND
        if index is None:
            d = xy - a
            s, t = d @ u, d @ n
            claimed |= ((s > -_CLAIM_END) & (s < L + _CLAIM_END)
                        & (np.abs(t) < r))
            continue
        sel = index.near_segment(a, u, n, r, -_CLAIM_END, L + _CLAIM_END)
        if not len(sel):
            continue
        d = xy[sel] - a
        s, t = d @ u, d @ n
        claimed[sel] |= ((s > -_CLAIM_END) & (s < L + _CLAIM_END)
                         & (np.abs(t) < r))
    return claimed

"""Synteettinen myymala JOKA ON KEILATTU — asemat, varjot, per-piste-totuus.

`_synth_retail.py` naytteistaa pinnat tasaisella tiheydella joka suunnasta.
Se mittaa algoritmia, ei aineistoa, ja siksi se EI voi paljastaa mitaan
naista tunnetuista virhelahteista:

  - palkin uuma on katsomissuunnan takana eika sita keilata (kiinnitysportti
    hylkasi aidon palkin siita ettei sita nay)
  - yksipuolisen seinan paksuutta ei voi mitata koska ulkopintaa ei ole
  - yhdeksan GT-aukkoa ei loydy koska pilvessa ei ole reikaa
  - kaukainen pinta on harva ja lahella oleva tihea

Tama generoi ehdokaspinnat ja ajaa niiden lapi jokaisen ASEMAN kulmapuskurin:
sade osuu vain lahimpaan pintaan, jyrka kohtauskulma ei palauta, ja tiheys
laskee etaisyyden nelioon kuten oikeassa keilauksessa. Lopputulos on pilvi
jossa on varjot, tiheysvaihtelu ja yksipuoliset seinat — ja jokaisella
pisteella on TOTUUS mukana.

Ulostulo on Rohbau3D-yhteensopiva, joten koko olemassa oleva GT-pino
(`_rohbau_qa`, `_wall_inst_qa`, `_opening_qa`, `_beam_qa`, `_column_qa`)
toimii siihen sellaisenaan:

    <out>/cloud.ply      binaari-PLY (xyz float32)
    <out>/coord.npy      Nx3 float32, mm
    <out>/class.npy      Rohbau-luokka per piste (5=Wall, 9=Beam, 10=Column…)
    <out>/instance.npy   instanssitunnus per piste
    <out>/s3dis.npy      S3DIS-luokka per piste (koulutusta varten)
    <out>/stations.npy   asemien origot
    <out>/gt.json        akselit, pilarit, palkit, aukot, hyllynetupinnat

Kaytto:
    _synth_store.py --out data/_store_a --sx 60000 --sy 40000
    _synth_store.py --out data/_store_big --sx 140000 --sy 90000 --seed 3
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# Rohbau3D-luokat (data/_rohbau_qa.py::_REG)
R_NONE, R_CEIL, R_FLOOR = 0, 1, 4
R_WALL, R_DRYWALL, R_CUTOUT, R_PARAPET = 5, 6, 7, 8
R_BEAM, R_COLUMN, R_WINDOW, R_DOOR = 9, 10, 13, 14
R_FACADE, R_TGA = 15, 17

# S3DIS (pointnet_filter: 0=ceiling 1=floor 2=wall 3=beam 4=column …)
S_CEIL, S_FLOOR, S_WALL, S_BEAM, S_COL = 0, 1, 2, 3, 4
S_WINDOW, S_DOOR, S_TABLE, S_CHAIR, S_SOFA = 5, 6, 7, 8, 9
S_BOOKCASE, S_BOARD, S_CLUTTER = 10, 11, 12

# kind -> (Rohbau, S3DIS)
KINDS = {
    "wall":     (R_WALL, S_WALL),
    "drywall":  (R_DRYWALL, S_WALL),
    "glass":    (R_WINDOW, S_WINDOW),
    "door":     (R_DOOR, S_DOOR),
    "window":   (R_WINDOW, S_WINDOW),
    "floor":    (R_FLOOR, S_FLOOR),
    "ceiling":  (R_CEIL, S_CEIL),
    "column":   (R_COLUMN, S_COL),
    "beam":     (R_BEAM, S_BEAM),
    "shelf":    (R_NONE, S_BOOKCASE),
    "fridge":   (R_NONE, S_BOOKCASE),
    "rack":     (R_NONE, S_BOOKCASE),
    "counter":  (R_NONE, S_TABLE),
    "tga":      (R_TGA, S_CLUTTER),
    "clutter":  (R_NONE, S_CLUTTER),
}


class Parts:
    """Ehdokaspinnat: pisteet + normaali + luokka + instanssi."""

    def __init__(self, step: float, rng) -> None:
        self.step = step
        self.rng = rng
        self._xyz: list[np.ndarray] = []
        self._nrm: list[np.ndarray] = []
        self._kind: list[np.ndarray] = []
        self._inst: list[np.ndarray] = []
        self._next = 1
        self.kind_names: list[str] = list(KINDS)

    def _add(self, pts, nrm, kind: str, inst: int, keep: float) -> None:
        if len(pts) == 0:
            return
        if keep < 1.0:
            pts = pts[self.rng.random(len(pts)) < keep]
            if len(pts) == 0:
                return
        self._xyz.append(pts.astype(np.float32))
        self._nrm.append(np.tile(np.asarray(nrm, np.float32), (len(pts), 1)))
        self._kind.append(np.full(len(pts), self.kind_names.index(kind), np.int16))
        self._inst.append(np.full(len(pts), inst, np.int32))

    def new_inst(self) -> int:
        self._next += 1
        return self._next - 1

    def face(self, p0, p1, z0, z1, kind, inst, side=+1, keep=1.0, step=None) -> None:
        """Pystypinta janalta p0->p1; side valitsee kumpaan suuntaan normaali osoittaa."""
        s = step or self.step
        p0 = np.asarray(p0, float)
        p1 = np.asarray(p1, float)
        u = p1 - p0
        L = float(np.linalg.norm(u))
        if L < s or z1 - z0 < s:
            return
        u /= L
        n = np.array([-u[1], u[0]]) * side
        S, Z = np.meshgrid(np.arange(0.0, L, s), np.arange(z0, z1, s))
        xy = p0[None, :] + S.ravel()[:, None] * u[None, :]
        pts = np.column_stack([xy[:, 0], xy[:, 1], Z.ravel()])
        self._add(pts, (n[0], n[1], 0.0), kind, inst, keep)

    def slab(self, x0, x1, y0, y1, z, kind, inst, up=True, keep=1.0, step=None) -> None:
        s = step or self.step
        if x1 - x0 < s or y1 - y0 < s:
            return
        X, Y = np.meshgrid(np.arange(x0, x1, s), np.arange(y0, y1, s))
        pts = np.column_stack([X.ravel(), Y.ravel(), np.full(X.size, float(z))])
        self._add(pts, (0.0, 0.0, 1.0 if up else -1.0), kind, inst, keep)

    def sides(self, x0, x1, y0, y1, z0, z1, kind, inst, which=("x-", "x+", "y-", "y+"),
              keep=1.0) -> None:
        """Laatikon pystysivut ULOSPAIN osoittavin normaalein.

        Suunta on tassa yhdessa paikassa: kalusteen etupinta jonka normaali
        osoittaa runkoon pain on jokaiselle asemalle takapinta ja katoaa
        pilvesta kokonaan. Nain kavi ensimmaisessa versiossa — gondolien ja
        kylmakaappien etupinnat puuttuivat, ja jaljelle jaivat vain
        hyllytasot ylhaalta nahtyna.
        """
        seg = {"y-": ((x0, y0), (x1, y0)), "x+": ((x1, y0), (x1, y1)),
               "y+": ((x1, y1), (x0, y1)), "x-": ((x0, y1), (x0, y0))}
        for w in which:
            a, b = seg[w]
            self.face(a, b, z0, z1, kind, inst, side=-1, keep=keep)

    def hpatch(self, a, b, width, z, kind, inst, up=False, keep=1.0) -> None:
        """Vaakalaikku janan a->b ymparille, leveys kohtisuoraan janasta."""
        a = np.asarray(a, float)
        b = np.asarray(b, float)
        L = float(np.linalg.norm(b - a))
        if L < self.step or width < self.step:
            return
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        S, O = np.meshgrid(np.arange(0.0, L, self.step),
                           np.arange(-width / 2.0, width / 2.0, self.step))
        xy = (a[None, :] + S.ravel()[:, None] * u[None, :]
              + O.ravel()[:, None] * n[None, :])
        pts = np.column_stack([xy[:, 0], xy[:, 1], np.full(len(xy), float(z))])
        self._add(pts, (0.0, 0.0, 1.0 if up else -1.0), kind, inst, keep)

    def box(self, x0, x1, y0, y1, z0, z1, kind, inst, keep=1.0, top=True) -> None:
        self.sides(x0, x1, y0, y1, z0, z1, kind, inst, keep=keep)
        if top:
            self.slab(x0, x1, y0, y1, z1, kind, inst, up=True, keep=keep)

    def finish(self):
        return (np.vstack(self._xyz), np.vstack(self._nrm),
                np.concatenate(self._kind), np.concatenate(self._inst))


def scan(data, stations, ang_deg: float, max_range: float, min_cos: float,
         noise_mm: float, reg_mm: float, rng, chunk: int = 4_000_000):
    """Kulmapuskuri per asema: sade palauttaa vain lahimman pinnan.

    Tama tuottaa kolme asiaa joita tasainen naytteistys ei tuota: VARJOT
    (lahempi pinta peittaa kauemman), TIHEYSVAIHTELUN (bini on kulma, joten
    kaukainen pinta on harva) ja YKSIPUOLISET SEINAT (ulkopintaa ei nae
    yksikaan sisalla oleva asema). Jyrka kohtauskulma ei palauta lainkaan
    (``min_cos``), ja jokaisella asemalla on oma rekisterointivirheensa.
    """
    xyz, nrm, kind, inst = data
    naz = int(round(360.0 / ang_deg))
    nel = int(round(180.0 / ang_deg))
    nbin = naz * nel
    keep_xyz, keep_kind, keep_inst = [], [], []
    for st in stations:
        st = np.asarray(st, np.float64)
        best_d = np.full(nbin, np.inf, np.float32)
        best_i = np.full(nbin, -1, np.int64)
        for s in range(0, len(xyz), chunk):
            e = min(s + chunk, len(xyz))
            d = xyz[s:e].astype(np.float64) - st
            dist = np.sqrt((d * d).sum(1))
            ok = (dist > 500.0) & (dist < max_range)
            if not ok.any():
                continue
            idx = np.flatnonzero(ok)
            d, dist = d[idx], dist[idx]
            u = d / dist[:, None]
            cos = -(u * nrm[s:e][idx]).sum(1)
            hit = cos > min_cos
            if not hit.any():
                continue
            idx, d, dist, u = idx[hit], d[hit], dist[hit], u[hit]
            el = np.degrees(np.arcsin(np.clip(u[:, 2], -1.0, 1.0)))
            vis = el > -60.0
            if not vis.any():
                continue
            idx, dist, u, el = idx[vis], dist[vis], u[vis], el[vis]
            az = np.degrees(np.arctan2(u[:, 1], u[:, 0])) % 360.0
            key = (np.minimum((az / ang_deg).astype(np.int64), naz - 1) * nel
                   + np.minimum(((el + 90.0) / ang_deg).astype(np.int64), nel - 1))
            order = np.lexsort((dist, key))
            k_s, d_s, i_s = key[order], dist[order], idx[order]
            first = np.flatnonzero(np.r_[True, k_s[1:] != k_s[:-1]])
            kk, dd, ii = k_s[first], d_s[first].astype(np.float32), i_s[first] + s
            win = dd < best_d[kk]
            best_d[kk[win]] = dd[win]
            best_i[kk[win]] = ii[win]
        sel = best_i[best_i >= 0]
        if not len(sel):
            continue
        p = xyz[sel].astype(np.float64)
        p = p + nrm[sel] * rng.normal(0.0, noise_mm, (len(sel), 1))
        p = p + rng.normal(0.0, reg_mm, 3)
        keep_xyz.append(p.astype(np.float32))
        keep_kind.append(kind[sel])
        keep_inst.append(inst[sel])
    return (np.vstack(keep_xyz), np.concatenate(keep_kind),
            np.concatenate(keep_inst))


def build_store(P: Parts, sx: float, sy: float, h: float, rng) -> dict:
    """Big-box-myymala oikeilla kalustemitoilla.

    Mitat ovat kalustemittoja eivatka detektorin toiveita: gondoli 1800 mm
    (pystymaskin PITAA pudottaa se), seinahylly 2400 mm hyllyvalilla 450 mm,
    kylmakaappi 2100 mm lasiovin (lattiasta kattoon ulottuva pystypinta jonka
    TAKANA on vaakatasoja — juuri se tapaus jolla hyllyportin kynnys mitataan),
    lavahylly 5400 mm tasovalilla 1800 mm.
    """
    gt: dict = {"walls": [], "columns": [], "beams": [], "openings": [],
                "shelf_faces": [], "footprints": [], "floor_z": 0.0,
                "ceiling_z": h}
    T_EXT = float(rng.choice([200.0, 250.0, 300.0]))
    T_BOH = float(rng.choice([150.0, 200.0]))
    T_ROOM = float(rng.choice([92.0, 120.0]))
    col_pitch = float(rng.uniform(7200.0, 8800.0))
    col_side = float(rng.choice([350.0, 400.0, 500.0]))
    beam_w = float(rng.uniform(300.0, 500.0))
    beam_d = float(rng.uniform(600.0, 900.0))
    aisle = float(rng.uniform(3200.0, 4200.0))
    gond_h = float(rng.uniform(1600.0, 2100.0))
    gond_deck = float(rng.uniform(350.0, 450.0))
    gond_w = float(rng.uniform(1100.0, 1500.0))
    shelf_h = float(rng.uniform(2200.0, 2600.0))
    shelf_d = float(rng.uniform(800.0, 1000.0))
    fr_h = float(rng.uniform(2000.0, 2200.0))
    fr_d = float(rng.uniform(800.0, 1000.0))
    boh_fx = float(rng.uniform(0.60, 0.76))
    boh_fy = float(rng.uniform(0.26, 0.40))

    def wall(p0, p1, t, kind="wall", gaps=(), keep=1.0, two_sided=True, z1=None):
        p0 = np.asarray(p0, float)
        p1 = np.asarray(p1, float)
        zt = h if z1 is None else z1
        L = float(np.linalg.norm(p1 - p0))
        u = (p1 - p0) / L
        n = np.array([-u[1], u[0]])
        inst = P.new_inst()
        gs = [(g[0], g[1], g[2], g[3] if len(g) > 3 else 0.0) for g in gaps]
        spans = []
        cur = 0.0
        for s0, s1, head, sill in sorted(gs):
            if s0 > cur:
                spans.append((cur, s0, 20.0, zt - 20.0))
            spans.append((s0, s1, head, zt - 20.0))
            if sill > 0.0:
                spans.append((s0, s1, 20.0, sill))
            cur = s1
        if cur < L:
            spans.append((cur, L, 20.0, zt - 20.0))
        for s0, s1, za, zb in spans:
            a, b = p0 + s0 * u, p0 + s1 * u
            sides = (+1, -1) if two_sided else (+1,)
            for sgn in sides:
                P.face(a + sgn * (t / 2) * n, b + sgn * (t / 2) * n, za, zb,
                       kind, inst, side=sgn, keep=keep)
        for s0, s1, head, sill in gs:
            # Aukon PIELET, ylityspalkin alapinta ja ikkunan sisapielen ylapinta.
            # Ilman niita aukko on pelkka rako eika siina ole yhtaan pistetta,
            # jolloin aukkodetektiota ei voi mitata — oikea keilaus nakee
            # pielen aina.
            oi = P.new_inst()
            okind = "window" if sill > 0.0 else "door"
            for sN, sgn in ((s0, -1), (s1, +1)):
                c = p0 + sN * u
                P.face(c - (t / 2) * n, c + (t / 2) * n, max(sill, 20.0), head,
                       okind, oi, side=sgn)
            P.hpatch(p0 + s0 * u, p0 + s1 * u, t, head, okind, oi, up=False)
            if sill > 0.0:
                P.hpatch(p0 + s0 * u, p0 + s1 * u, t, sill, okind, oi, up=True)
        gt["walls"].append({"axis": [list(p0), list(p1)], "thickness": t})
        for s0, s1, head, sill in gs:
            ctr = p0 + ((s0 + s1) / 2.0) * u
            gt["openings"].append({"center": [float(ctr[0]), float(ctr[1])],
                                   "width": float(s1 - s0),
                                   "height": float(head - sill),
                                   "sill": float(sill),
                                   "type": "window" if sill > 0.0 else "door"})
        return inst

    P.slab(-T_EXT, sx + T_EXT, -T_EXT, sy + T_EXT, 0.0, "floor", P.new_inst())
    P.slab(-T_EXT, sx + T_EXT, -T_EXT, sy + T_EXT, h, "ceiling", P.new_inst(), up=False)

    # Myymalan julkisivu on lasiruutuja pilarien valissa, ei yhta 12 m ikkunaa:
    # yksi pitka lasikaista antaisi GT:hen yhden 12 m aukkoinstanssin jota
    # mikaan detektori ei voi loytaa aukkona.
    g0, g1 = 0.14 * sx, 0.34 * sx
    pane, mull = 2400.0, 300.0
    panes = []
    x = g0
    while x + pane <= g1:
        panes.append((x - g0 + mull, x - g0 + mull + pane, 3000.0, 200.0))
        x += pane + mull
    wall((0, 0), (g0, 0), T_EXT)
    wall((g0, 0), (g1, 0), T_EXT, gaps=panes)
    wall((g1, 0), (sx, 0), T_EXT)
    for ps0, ps1, head, sill in panes:
        gi = P.new_inst()
        P.face((g0 + ps0, 0.0), (g0 + ps1, 0.0), sill, head, "glass", gi,
               side=+1, keep=0.05)
    for p0, p1 in (((sx, 0), (sx, sy)), ((sx, sy), (0, sy)), ((0, sy), (0, 0))):
        wall(p0, p1, T_EXT)

    bx, by = boh_fx * sx, boh_fy * sy
    wall((bx, 0), (bx, by), T_BOH, kind="drywall",
         gaps=[(0.40 * by, 0.40 * by + 2400, 2400)])
    wall((bx, by), (sx, by), T_BOH, kind="drywall",
         gaps=[(0.28 * (sx - bx), 0.28 * (sx - bx) + 2400, 2400)])
    for frac in (0.34, 0.67):
        x = bx + frac * (sx - bx)
        wall((x, 0), (x, by), T_ROOM, kind="drywall", gaps=[(1800, 2700, 2100)])
    wall((bx, 0.55 * by), (sx, 0.55 * by), T_ROOM, kind="drywall",
         gaps=[(2200, 3100, 2100), (0.55 * (sx - bx), 0.55 * (sx - bx) + 900, 2100)])

    C = col_side
    for cx in np.arange(col_pitch, sx - 3000.0, col_pitch):
        for cy in np.arange(col_pitch, sy - 3000.0, col_pitch):
            inst = P.new_inst()
            P.box(cx - C / 2, cx + C / 2, cy - C / 2, cy + C / 2, 20.0, h - 20.0,
                  "column", inst, top=False)
            gt["columns"].append([float(cx), float(cy)])

    # Palkki on jannevali pilarilta pilarille, ei yksi rakennuksen mittainen
    # kappale: yhtena instanssina kirjattu 60 m palkki nayttaa mallin
    # pirstoutuvan 11.5-kertaisesti, vaikka putki katkaisee sen pilarien
    # kohdalta oikein (Rohbaussa sama luku on 1.4-1.6).
    bw, bd = beam_w, beam_d
    zb = h - bd
    col_x = list(np.arange(col_pitch, sx - 3000.0, col_pitch))
    spans = list(zip([0.0] + col_x, col_x + [sx]))
    for cy in np.arange(col_pitch, sy - 3000.0, col_pitch):
        for sx0, sx1 in spans:
            inst = P.new_inst()
            for sgn in (+1, -1):
                P.face((sx0, cy + sgn * bw / 2), (sx1, cy + sgn * bw / 2), zb,
                       h - 20.0, "beam", inst, side=sgn)
            P.slab(sx0, sx1, cy - bw / 2, cy + bw / 2, zb, "beam", inst, up=False)
            gt["beams"].append({"axis": [[float(sx0), float(cy)],
                                         [float(sx1), float(cy)]],
                                "width": bw, "soffit_z": float(zb), "depth": bd})

    dw, dh = 600.0, 400.0
    for cy in np.arange(0.5 * col_pitch, sy - 2000.0, col_pitch):
        inst = P.new_inst()
        zt = h - bd - 250.0
        P.box(0.02 * sx, bx, cy - dw / 2, cy + dw / 2, zt - dh, zt, "tga", inst)

    def _goods(x0, x1, y0, y1, z, gh, which, inst, kind) -> None:
        """Tavara hyllytasolla: laatikkorivi etureunaan, satunnainen korkeus.

        Tyhja hyllyrunko ei ole se mita keilaus nakee. Myymalassa tason paalla
        on tavaraa joka tayttaa valin ja tuottaa sen vaakarakenteen jota
        hyllysaannon todiste etsii — ilman sita mitataan kalustetta jota ei
        ole olemassa.
        """
        along_y = (y1 - y0) > (x1 - x0)
        depth = min(0.75 * ((x1 - x0) if along_y else (y1 - y0)), 700.0)
        for side in which:
            if along_y and side not in ("x-", "x+"):
                continue
            if not along_y and side not in ("y-", "y+"):
                continue
            if along_y:
                gx0 = x0 if side == "x-" else x1 - depth
                gx1 = gx0 + depth
                span0, span1 = y0, y1
            else:
                gy0 = y0 if side == "y-" else y1 - depth
                gy1 = gy0 + depth
                span0, span1 = x0, x1
            t = span0
            while t < span1 - 300.0:
                wdt = float(rng.uniform(280.0, 520.0))
                hgt = float(rng.uniform(0.45, 0.95)) * gh
                if along_y:
                    P.box(gx0, gx1, t, min(t + wdt, span1), z, z + hgt, kind,
                          inst, top=True)
                else:
                    P.box(t, min(t + wdt, span1), gy0, gy1, z, z + hgt, kind,
                          inst, top=True)
                t += wdt + float(rng.uniform(10.0, 60.0))

    def fixture(x0, x1, y0, y1, height, decks, kind, which, glass=False,
                face_line=None, goods=True):
        """Kaluste laatikkona: valitut pystysivut, hyllytasot ja kansi.

        ``which`` kertoo mitka sivut ovat nakyvissa — seinaa vasten oleva
        kaluste ei nayta takasivuaan. ``face_line`` kirjataan GT:hen sina
        etupintana jota hyllysaanto tuomitsee.
        """
        inst = P.new_inst()
        P.sides(x0, x1, y0, y1, 20.0, height, kind, inst, which=which,
                keep=0.05 if glass else 1.0)
        for z in np.arange(400.0, height - 200.0, decks):
            P.slab(x0, x1, y0, y1, z, kind, inst, up=True, step=P.step * 2)
            P.slab(x0, x1, y0, y1, z - 25.0, kind, inst, up=False, step=P.step * 2)
            if goods:
                _goods(x0, x1, y0, y1, z, min(decks - 120.0, 380.0), which,
                       inst, kind)
        P.slab(x0, x1, y0, y1, height, kind, inst, up=True)
        P.slab(x0, x1, y0, y1, height - 25.0, kind, inst, up=False)
        gt["footprints"].append([float(x0), float(x1), float(y0), float(y1)])
        if face_line is not None:
            gt["shelf_faces"].append(face_line)
        return inst

    ay0, ay1 = 0.08 * sy, 0.94 * sy
    gx = 0.10 * sx
    while gx < bx - 4000.0:
        fixture(gx - gond_w / 2, gx + gond_w / 2, ay0, ay1, gond_h, gond_deck,
                "shelf", ("x-", "x+"))
        gx += aisle

    sh_d, sh_h = shelf_d, shelf_h
    y_back = sy - T_EXT / 2 - sh_d
    sx_shelf0, sx_shelf1 = 0.02 * sx, bx - 4000.0
    fixture(sx_shelf0, sx_shelf1, y_back, y_back + sh_d, sh_h, 450.0, "shelf",
            ("y-",), face_line=[[sx_shelf0, y_back], [sx_shelf1, y_back]])

    fx0 = T_EXT / 2
    fy = 0.10 * sy
    while fy < 0.45 * sy:
        fixture(fx0, fx0 + fr_d, fy, fy + 3600.0, fr_h, 400.0, "fridge",
                ("x+",), face_line=[[fx0 + fr_d, fy], [fx0 + fr_d, fy + 3600.0]])
        fy += 4000.0
    while fy < 0.88 * sy:
        fixture(fx0, fx0 + 800.0, fy, fy + 2400.0, fr_h, 450.0, "fridge",
                ("x+",), glass=True,
                face_line=[[fx0 + 800.0, fy], [fx0 + 800.0, fy + 2400.0]])
        fy += 2800.0

    rk_h = min(5400.0, h - 1500.0)
    for ry in np.arange(2500.0, by - 2500.0, 3000.0):
        inst = P.new_inst()
        for rx in np.arange(bx + 1500.0, sx - 2000.0, 2800.0):
            for ux in (rx, rx + 2700.0):
                P.box(ux - 50, ux + 50, ry - 550, ry + 550, 20.0, rk_h, "rack", inst)
        gt["footprints"].append([float(bx + 1500.0), float(sx - 2000.0),
                                 float(ry - 550), float(ry + 550)])
        for z in np.arange(0.0, rk_h, 1800.0):
            if z > 0:
                P.slab(bx + 1500.0, sx - 2000.0, ry - 550, ry + 550, z, "rack",
                       inst, up=True, step=P.step * 2)

    for i, cx in enumerate(np.arange(0.16 * sx, 0.32 * sx, 2200.0)):
        inst = P.new_inst()
        P.box(cx, cx + 1600.0, 2500.0, 3400.0, 20.0, 1100.0, "counter", inst)
        gt["footprints"].append([float(cx), float(cx + 1600.0), 2500.0, 3400.0])
    return gt


def stations_for(sx: float, sy: float, h: float, gt: dict, pitch: float,
                 z: float = 1650.0) -> np.ndarray:
    """Asemat kulkuvaylille: tihea ehdokasruudukko + minimietaisyys.

    Keilain seisoo siella missa mahtuu seisomaan. Harva ruudukko ei sovi
    kaytavajakoon: 3.6 m gondolivalilla se osuu kalusteen paalle ja putoaa,
    jolloin asemia jaa 17 kappaletta 2400 m2:lle eli yksi per 141 m2 — oikea
    myymalakeilaus on yksi per 50-80 m2. Tihea ehdokasjoukko loytaa kaytavat
    itse, ja minimietaisyys pitaa maaran realistisena.
    """
    fps = gt.get("footprints", [])
    cols = gt.get("columns", [])
    cand = []
    for x in np.arange(1800.0, sx - 1000.0, 900.0):
        for y in np.arange(1800.0, sy - 1000.0, 900.0):
            if any(abs(x - c[0]) < 900 and abs(y - c[1]) < 900 for c in cols):
                continue
            if any(fx0 - 500 < x < fx1 + 500 and fy0 - 500 < y < fy1 + 500
                   for fx0, fx1, fy0, fy1 in fps):
                continue
            cand.append((x, y))
    if not cand:
        return np.empty((0, 3))
    rng = np.random.default_rng(7)
    cand = np.asarray(cand, float)
    cand = cand[rng.permutation(len(cand))]
    out: list[list[float]] = []
    for x, y in cand:
        if all((x - p[0]) ** 2 + (y - p[1]) ** 2 > pitch * pitch for p in out):
            out.append([x, y, z])
    out.sort(key=lambda p: (p[1], p[0]))
    return np.asarray(out, float)


def write_ply(path: Path, pts: np.ndarray) -> None:
    with open(path, "wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"element vertex {len(pts)}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\nend_header\n")
        f.write(np.ascontiguousarray(pts, dtype="<f4").tobytes())


def generate(out: Path, sx: float, sy: float, h: float, step: float, ang: float,
             rng_seed: int, max_range: float, pitch: float, noise: float,
             reg: float, min_cos: float, write_cloud: bool = True) -> dict:
    """Yksi skene levylle. Palauttaa manifestirivin."""
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(rng_seed)
    P = Parts(step, rng)
    gt = build_store(P, sx, sy, h, rng)
    data = P.finish()
    st = stations_for(sx, sy, h, gt, pitch)
    pts, kind, inst = scan(data, st, ang, max_range, min_cos, noise, reg, rng)
    names = list(KINDS)
    rcls = np.array([KINDS[n][0] for n in names], np.int16)[kind]
    scls = np.array([KINDS[n][1] for n in names], np.int16)[kind]
    np.save(out / "coord.npy", pts.astype(np.float32))
    np.save(out / "class.npy", rcls.astype(np.int8))
    np.save(out / "instance.npy", inst.astype(np.int32))
    np.save(out / "s3dis.npy", scls.astype(np.int8))
    np.save(out / "stations.npy", st)
    if write_cloud:
        write_ply(out / "cloud.ply", pts)
    gt["n_points"] = int(len(pts))
    gt["size"] = [sx, sy, h]
    gt["stations"] = int(len(st))
    gt["seed"] = int(rng_seed)
    gt["scan"] = {"step": step, "ang": ang, "pitch": pitch, "range": max_range,
                  "noise": noise, "reg": reg}
    (out / "gt.json").write_text(json.dumps(gt, indent=1), encoding="utf-8")
    return {"dir": out.name, "points": int(len(pts)), "stations": int(len(st)),
            "size_m": [round(sx / 1000, 1), round(sy / 1000, 1), round(h / 1000, 1)],
            "walls": len(gt["walls"]), "columns": len(gt["columns"]),
            "beams": len(gt["beams"]), "openings": len(gt["openings"]),
            "shelf_faces": len(gt["shelf_faces"]), "seed": int(rng_seed),
            "ang": ang, "pitch": pitch}


def batch(root: Path, n: int, seed0: int, write_cloud: bool,
          sx_max: float, sy_max: float, h_max: float) -> None:
    """Monta skeneä koulutusta varten: eri pohja, eri kalustejako, eri keilaus.

    Yksi skene ei ole koulutusaineisto vaan yksi näyte. Vaihtelu on tässä
    tarkoituksellisesti sellaista jonka putki NÄKEE: pohjan mitat, pilariväli,
    käytäväjako, kalustekorkeudet, asemaväli ja keilaimen kulmaresoluutio.
    """
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(n):
        rng = np.random.default_rng(10_000 + seed0 + i)
        sx = float(rng.uniform(0.35, 1.0) * sx_max)
        sy = float(rng.uniform(0.35, 1.0) * sy_max)
        h = float(rng.uniform(0.62, 1.0) * h_max)
        ang = float(rng.choice([0.16, 0.20, 0.25]))
        pitch = float(rng.uniform(6_000, 9_500))
        step = float(rng.choice([15.0, 18.0, 22.0]))
        noise = float(rng.uniform(1.5, 4.0))
        reg = float(rng.uniform(1.0, 6.0))
        d = root / f"scene_{i:02d}"
        print(f"[{i + 1}/{n}] {d.name}  {sx / 1000:.0f}x{sy / 1000:.0f} m  "
              f"h={h / 1000:.1f}  ang={ang}  pitch={pitch / 1000:.1f} m", flush=True)
        row = generate(d, sx, sy, h, step, ang, 20_000 + seed0 + i, 35_000.0,
                       pitch, noise, reg, 0.12, write_cloud)
        print(f"      {row['points']:,} pistettä, {row['stations']} asemaa, "
              f"{row['walls']} seinää, {row['columns']} pilaria", flush=True)
        rows.append(row)
        (root / "manifest.json").write_text(
            json.dumps({"scenes": rows}, indent=1), encoding="utf-8")
    tot = sum(r["points"] for r in rows)
    print(f"valmis: {len(rows)} skenea, {tot:,} pistetta yhteensa")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/_store_a")
    ap.add_argument("--sx", type=float, default=60000.0)
    ap.add_argument("--sy", type=float, default=40000.0)
    ap.add_argument("--height", type=float, default=7000.0)
    ap.add_argument("--step", type=float, default=18.0, help="ehdokaspintojen tiheys mm")
    ap.add_argument("--ang", type=float, default=0.14, help="keilaimen kulmaresoluutio deg")
    ap.add_argument("--range", type=float, default=35000.0, help="asemien kantama mm")
    ap.add_argument("--pitch", type=float, default=9000.0, help="asemavali mm")
    ap.add_argument("--noise", type=float, default=2.5, help="kohina mm")
    ap.add_argument("--reg", type=float, default=3.0, help="rekisterointivirhe mm/asema")
    ap.add_argument("--min-cos", type=float, default=0.12, help="jyrkin palauttava kulma")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scenes", type=int, default=0,
                    help="generoi N skeneä --out-hakemistoon (koulutusaineisto)")
    ap.add_argument("--no-ply", action="store_true",
                    help="jätä cloud.ply kirjoittamatta (npy riittää koulutukseen)")
    a = ap.parse_args()

    if a.scenes > 0:
        # eraajossa --sx/--sy/--height ovat YLARAJAT, ei kiintea koko
        batch(Path(a.out), a.scenes, a.seed, not a.no_ply,
              a.sx, a.sy, a.height)
        return

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)

    P = Parts(a.step, rng)
    gt = build_store(P, a.sx, a.sy, a.height, rng)
    data = P.finish()
    print(f"ehdokaspintoja {len(data[0]):,}", flush=True)

    st = stations_for(a.sx, a.sy, a.height, gt, a.pitch)
    print(f"asemia {len(st)}", flush=True)

    pts, kind, inst = scan(data, st, a.ang, a.range, a.min_cos, a.noise, a.reg, rng)
    names = list(KINDS)
    rcls = np.array([KINDS[n][0] for n in names], np.int16)[kind]
    scls = np.array([KINDS[n][1] for n in names], np.int16)[kind]

    np.save(out / "coord.npy", pts.astype(np.float32))
    np.save(out / "class.npy", rcls.astype(np.int16))
    np.save(out / "instance.npy", inst.astype(np.int32))
    np.save(out / "s3dis.npy", scls.astype(np.int16))
    np.save(out / "stations.npy", st)
    write_ply(out / "cloud.ply", pts)
    gt["n_points"] = int(len(pts))
    gt["size"] = [a.sx, a.sy, a.height]
    gt["stations"] = int(len(st))
    (out / "gt.json").write_text(json.dumps(gt, indent=1), encoding="utf-8")

    print(f"{out}  {len(pts):,} pistetta  "
          f"({a.sx/1000:.0f}x{a.sy/1000:.0f} m, h={a.height/1000:.1f} m)")
    tot = len(pts)
    for n in names:
        c = int((kind == names.index(n)).sum())
        if c:
            print(f"  {n:9s} {c:>10,}  {c/tot:5.1%}")


if __name__ == "__main__":
    main()

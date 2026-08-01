"""MITTAKAAVA- JA LIIKETILATESTI: generoi synteettisen kauppahallin pistepilven.

Validointisetissa ei ole yhtaan liiketilaa eika mitaan asuntoa isompaa. Tama
tekee molemmat: parametrinen big-box-myymala (lattia-katto-hyllyt, pilarikentta,
lasijulkisivu, taustatilat) jonka POHJA ON TUNNETTU -> sama tiedosto kelpaa
seka skaalausmittaukseen etta tarkkuuden ground-truthiksi.

Kirjoitetaan lohkoittain binaari-PLY:na (float32 xyz, little-endian) -> osuu
loaderin muistirajattuun kaistalukupolkuun kuten oikea jattiskanni.

Aja:  .venv\\Scripts\\python data/_synth_retail.py --step 12 --out data/_retail.ply
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

NOISE_MM = 3.0          # TLS-luokan kohina
GLASS_KEEP = 0.04       # lasi palauttaa vain rippeen (reunat, lika, tarrat)


class PlyWriter:
    """Kirjoittaa float32-xyz-PLY:n lohkoittain; pistemaara paikataan headeriin lopuksi."""

    def __init__(self, path: Path):
        self.path = path
        self.n = 0
        self._f = open(path, "wb")
        self._header_n_pos = 0
        head = (
            "ply\n"
            "format binary_little_endian 1.0\n"
            "element vertex "
        )
        self._f.write(head.encode())
        self._header_n_pos = self._f.tell()
        self._f.write(b"00000000000\n")
        self._f.write(
            b"property float x\nproperty float y\nproperty float z\nend_header\n"
        )

    def add(self, pts: np.ndarray) -> None:
        if len(pts) == 0:
            return
        self._f.write(np.ascontiguousarray(pts, dtype="<f4").tobytes())
        self.n += len(pts)

    def close(self) -> None:
        self._f.seek(self._header_n_pos)
        self._f.write(f"{self.n:011d}".encode())
        self._f.close()


def _rect(rng, p0, p1, z0, z1, step, keep=1.0):
    """Pystytaso janalta p0->p1 korkeusvalille [z0, z1]."""
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    u = p1 - p0
    L = float(np.linalg.norm(u))
    if L < step or z1 - z0 < step:
        return np.empty((0, 3))
    u /= L
    ns = int(L / step) + 1
    nz = int((z1 - z0) / step) + 1
    S, Z = np.meshgrid(np.linspace(0, L, ns), np.linspace(z0, z1, nz))
    xy = p0[None, :] + S.ravel()[:, None] * u[None, :]
    out = np.column_stack([xy[:, 0], xy[:, 1], Z.ravel()])
    if keep < 1.0:
        out = out[rng.random(len(out)) < keep]
    return out + rng.normal(0, NOISE_MM, out.shape)


def _slab(rng, x0, x1, y0, y1, z, step, keep=1.0):
    nx = int((x1 - x0) / step) + 1
    ny = int((y1 - y0) / step) + 1
    X, Y = np.meshgrid(np.linspace(x0, x1, nx), np.linspace(y0, y1, ny))
    out = np.column_stack([X.ravel(), Y.ravel(), np.full(X.size, float(z))])
    if keep < 1.0:
        out = out[rng.random(len(out)) < keep]
    return out + rng.normal(0, NOISE_MM, out.shape)


def _wall_faces(rng, p0, p1, t, z0, z1, step, w, gaps=(), keep=1.0, both=True):
    """Molemmat pinnat + oviaukot (gaps = [(s0, s1, korkeus), ...] mitattuna p0:sta)."""
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    u = p1 - p0
    L = float(np.linalg.norm(u))
    u /= L
    n = np.array([-u[1], u[0]])
    spans = []
    cur = 0.0
    for s0, s1, _h in sorted(gaps):
        if s0 > cur:
            spans.append((cur, s0, z0, z1))
        spans.append((s0, s1, z0 + _h, z1))   # aukon ylapuolinen palkki
        cur = s1
    if cur < L:
        spans.append((cur, L, z0, z1))
    for s0, s1, za, zb in spans:
        if s1 - s0 < step or zb - za < step:
            continue
        a = p0 + s0 * u
        b = p0 + s1 * u
        for sgn in ((+1, -1) if both else (+1,)):
            w.add(_rect(rng, a + sgn * (t / 2) * n, b + sgn * (t / 2) * n, za, zb, step, keep))


def build(out: np.ndarray | Path, step: float, sx: float, sy: float, h: float,
          seed: int = 0) -> dict:
    """sx, sy = hallin sisamitat mm; h = vapaa korkeus mm."""
    rng = np.random.default_rng(seed)
    w = PlyWriter(Path(out))
    T_EXT, T_BOH, T_ROOM = 250.0, 200.0, 120.0
    gt: dict = {"walls": [], "floor_z": 0.0, "ceiling_z": h, "columns": []}

    def wall(p0, p1, t, gaps=(), keep=1.0, both=True, z0=0.0, z1=None):
        z1 = h if z1 is None else z1
        _wall_faces(rng, p0, p1, t, z0 + 20, z1 - 20, step, w, gaps, keep, both)
        gt["walls"].append({"axis": [list(p0), list(p1)], "thickness": t})

    # --- ulkoseinat: sisapinta aina, ulkopinta ei (sisakeilaus) -------------
    glass0, glass1 = 0.14 * sx, 0.34 * sx        # sisaankaynnin lasijulkisivu
    _wall_faces(rng, (0, 0), (glass0, 0), T_EXT, 20, h - 20, step, w, (), 1.0, False)
    _wall_faces(rng, (glass0, 0), (glass1, 0), T_EXT, 20, h - 20, step, w, (),
                GLASS_KEEP, False)
    _wall_faces(rng, (glass1, 0), (sx, 0), T_EXT, 20, h - 20, step, w, (), 1.0, False)
    gt["walls"].append({"axis": [[0, 0], [sx, 0]], "thickness": T_EXT})
    for p0, p1 in (((sx, 0), (sx, sy)), ((sx, sy), (0, sy)), ((0, sy), (0, 0))):
        _wall_faces(rng, p0, p1, T_EXT, 20, h - 20, step, w, (), 1.0, False)
        gt["walls"].append({"axis": [list(p0), list(p1)], "thickness": T_EXT})

    # --- taustatilat (BOH) nurkkaan: aidosti kaksipuolisia seinia ------------
    bx, by = 0.66 * sx, 0.38 * sy
    door = (2400.0, 4400.0, 2100.0)
    wall((bx, 0), (bx, by), T_BOH, gaps=[(0.42 * by, 0.42 * by + 2000, 2100)])
    wall((bx, by), (sx, by), T_BOH, gaps=[(0.30 * (sx - bx), 0.30 * (sx - bx) + 2000, 2100)])
    for frac in (0.36, 0.68):
        x = bx + frac * (sx - bx)
        wall((x, 0), (x, by), T_ROOM, gaps=[door])
    wall((bx, 0.55 * by), (sx, 0.55 * by), T_ROOM,
         gaps=[(3000, 5000, 2100), (0.5 * (sx - bx), 0.5 * (sx - bx) + 2000, 2100)])

    # --- pilarikentta 8 m ----------------------------------------------------
    C = 400.0
    for cx in np.arange(8000.0, sx - 4000.0, 8000.0):
        for cy in np.arange(8000.0, sy - 4000.0, 8000.0):
            if cx > bx - 1000 and cy < by + 1000:
                continue
            a = np.array([cx - C / 2, cy - C / 2])
            b = np.array([cx + C / 2, cy + C / 2])
            for p0, p1 in ((a, (b[0], a[1])), ((b[0], a[1]), b),
                           (b, (a[0], b[1])), ((a[0], b[1]), a)):
                w.add(_rect(rng, p0, p1, 20, h - 20, step))
            gt["columns"].append([float(cx), float(cy)])

    # --- palkisto (paljas runko, tyypillinen big-box) ------------------------
    zb = h - 700.0
    for cy in np.arange(8000.0, sy - 4000.0, 8000.0):
        for sgn in (+1, -1):
            w.add(_rect(rng, (0, cy + sgn * 150), (sx, cy + sgn * 150), zb, h - 20, step))
        w.add(_slab(rng, 0, sx, cy - 150, cy + 150, zb, step))

    # --- LIIKETILAN YDINTESTI: hyllyt ---------------------------------------
    # (a) gondolit 1800 mm: pystymaskin PITAA pudottaa nama.
    gy0, gy1 = 0.10 * sy, 0.92 * sy
    for gx in np.arange(0.06 * sx, bx - 3000, 6000.0):
        for sgn in (+1, -1):
            w.add(_rect(rng, (gx + sgn * 600, gy0), (gx + sgn * 600, gy1), 300, 1800, step))
        w.add(_slab(rng, gx - 600, gx + 600, gy0, gy1, 1800, step))
        for zsh in (600.0, 1200.0):
            w.add(_slab(rng, gx - 600, gx + 600, gy0, gy1, zsh, step * 2))

    # (b) lattia-katto-hyllykot seinilla: geometria EI erota naita seinasta
    #     (etupinta yltaa lattiasta kattoon aivan kuten seina). Talla mitataan
    #     onko semanttinen suodatin oikeasti tarpeen -> seina 900 mm sisalla.
    rd = 900.0
    hh = h - 400.0
    gt["shelf_faces"] = []
    for x0, x1, y0, y1, front in (
        (0.0, bx, sy - T_EXT / 2 - rd, sy - T_EXT / 2, "y-"),
        (T_EXT / 2, T_EXT / 2 + rd, 0.0, sy, "x+"),
    ):
        if front == "y-":
            w.add(_rect(rng, (x0, y0), (x1, y0), 20, hh, step))
            gt["shelf_faces"].append([[x0, y0], [x1, y0]])
        else:
            w.add(_rect(rng, (x1, y0), (x1, y1), 20, hh, step))
            gt["shelf_faces"].append([[x1, y0], [x1, y1]])
        for zsh in np.arange(500.0, hh, 900.0):
            w.add(_slab(rng, x0, x1, y0, y1, zsh, step * 2))

    # --- lattia + katto ------------------------------------------------------
    w.add(_slab(rng, -T_EXT, sx + T_EXT, -T_EXT, sy + T_EXT, 0.0, step))
    w.add(_slab(rng, -T_EXT, sx + T_EXT, -T_EXT, sy + T_EXT, h, step))

    w.close()
    gt["n_points"] = w.n
    gt["size"] = [sx, sy, h]
    gt["step"] = step
    return gt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/_retail.ply")
    ap.add_argument("--step", type=float, default=12.0, help="pisteväli mm")
    ap.add_argument("--sx", type=float, default=72000.0)
    ap.add_argument("--sy", type=float, default=48000.0)
    ap.add_argument("--height", type=float, default=7000.0)
    a = ap.parse_args()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    gt = build(out, a.step, a.sx, a.sy, a.height)
    Path(str(out) + ".gt.json").write_text(json.dumps(gt, indent=1), encoding="utf-8")
    mb = out.stat().st_size / 1e6
    print(f"{out}  {gt['n_points']:,} pistettä  {mb:,.0f} MB  "
          f"({a.sx/1000:.0f}×{a.sy/1000:.0f} m, h={a.height/1000:.1f} m, step={a.step} mm)")


if __name__ == "__main__":
    main()

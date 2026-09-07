"""Erottaako VAAKATASOJEN maara hyllykon etupinnan aidosta kipsiseinasta?

`remove_shelf_front_walls` tuomitsee MUODOSTA: lyhyehko seina rinnakkain
300-1500 mm paassa paljon pidemmasta. Runkovaiheen rakennuksessa sama muoto on
aito kipsiseina julkisivun edessa — ja mitattuna (`_chain_gt_probe.py`,
scene_07002, normals) juuri se kutsu pudottaa viisi GT-seinaa mallista peitolla
1.00. Sama laji kuin muutkin kaatuneet portit: muoto on sama, asia eri.

AGENTS.md kirjaa mitatun erottimen: hyllyn valissa on toistuvia vaakatasoja
~900 mm valein, kipsiseinan valissa yksi (palkki). Tama mittaa sen molemmilta
puolilta suoraan GT:sta, ilman putkiajoa: Rohbaun vaarin poistetut vs.
myymaloiden aidot hyllynetupinnat.

Kaytto: _shelf_guard_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "src"))

RATIOS = (1.3, 1.5, 2.0)
_BIN = 50.0
_SEP = 300.0
_REACH_LO, _REACH_HI = 100.0, 1200.0
_MIN_PTS = 200


def _levels(pts, w):
    """Vaakatasojen maara kummallakin puolella, MEDIAANIIN suhteutettuna.

    `second_face._gap_has_shelves` kayttaa 4x keskiarvoa, mutta se on viritetty
    kapeaan valiin jossa pohjataso on lahes tyhja. Kaytavan levyisessa kaistassa
    pohjataso on korkea ja sama tasosarja jaa kynnyksen alle — mitattu
    retail_l:ssa 8969 vs pohjataso 2354 eli tasot ovat siella, kynnys ei nay.
    """
    a = np.asarray(w["axis"][0], float)[:2]
    b = np.asarray(w["axis"][1], float)[:2]
    L = float(np.linalg.norm(b - a))
    if L < 500.0:
        return {}
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    d = pts[:, :2] - a
    t, perp, z = d @ u, d @ n, pts[:, 2]
    z0 = float(w.get("z_min") or 0.0)
    h = float(w.get("height") or 0.0)
    zlo, zhi = z0 + 300.0, z0 + h - 300.0
    half = 0.5 * float(w.get("thickness") or 200.0)
    out = {r: 0 for r in RATIOS}
    for sign in (+1.0, -1.0):
        m = ((t >= 0) & (t <= L) & (z > zlo) & (z < zhi)
             & (sign * perp > half + _REACH_LO) & (sign * perp < half + _REACH_HI))
        if int(m.sum()) < _MIN_PTS:
            continue
        nb = max(10, int((zhi - zlo) / _BIN))
        hist, edges = np.histogram(z[m], bins=nb, range=(zlo, zhi))
        med = float(np.median(hist[hist > 0])) if (hist > 0).any() else 0.0
        if med <= 0:
            continue
        for r in RATIOS:
            pk = np.flatnonzero(hist >= r * med)
            if len(pk) == 0:
                continue
            cnt = 1 + int((np.diff(edges[pk]) > _SEP).sum())
            out[r] = max(out[r], cnt)
    return out


FACE = {5, 6, 8, 15}
WRONG = {"scene_07002": [6, 83, 84, 91, 95], "scene_07001": [8],
         "scene_07004": [43, 44]}


def _wall_from_points(P: np.ndarray) -> dict:
    xy = P[:, :2]
    c = xy.mean(axis=0)
    u = np.linalg.svd(xy - c, full_matrices=False)[2][0]
    t = (xy - c) @ u
    a, b = c + u * t.min(), c + u * t.max()
    z0, z1 = float(P[:, 2].min()), float(P[:, 2].max())
    return {"id": "gt", "axis": [list(a), list(b)], "z_min": z0,
            "height": z1 - z0, "thickness": 200.0}


def _rohbau(scene: Path, pts_cache: dict) -> None:
    G = np.load(scene / "coord.npy").astype(np.float64)
    if float(np.ptp(G[:, 0])) < 500.0:
        G = G * 1000.0
    C = np.load(scene / "class.npy")
    I = np.load(scene / "instance.npy")
    wrong = set(WRONG.get(scene.name, []))
    rows = []
    for k in np.unique(I):
        m = I == k
        if m.sum() < 2000 or not np.isin(C[m], list(FACE)).any():
            continue
        P = G[m]
        L = float(np.linalg.norm(np.ptp(P[:, :2], axis=0)))
        if L < 1500.0:
            continue
        lv = _levels(G, _wall_from_points(P))
        rows.append((int(k), L / 1000.0, lv, int(k) in wrong))
    print(f"\n{scene.name}: {len(rows)} GT-seinainstanssia")
    head = " ".join(f"x{r:>5}" for r in RATIOS)
    print(f"  {'inst':>5} {'pituus':>7} {head}  tila")
    for k, L, lv, bad in sorted(rows, key=lambda r: (not r[3], r[0])):
        cells = " ".join(f"{lv.get(r, 0):6d}" for r in RATIOS)
        print(f"  {k:>5} {L:6.1f} m {cells}  {'VAARIN POISTETTU' if bad else ''}")
    for r in RATIOS:
        bads = [lv.get(r, 0) for _, _, lv, b in rows if b]
        rest = [lv.get(r, 0) for _, _, lv, b in rows if not b]
        print(f"  x{r}: vaarin poistetut {sorted(bads)}   muut med "
              f"{np.median(rest) if rest else 0:.0f} max {max(rest) if rest else 0}")


def _retail(ply: Path, gt: Path) -> None:
    import open3d as o3d
    g = json.loads(gt.read_text(encoding="utf-8"))
    faces = g.get("shelf_faces") or []
    if not faces:
        return
    pts = np.asarray(o3d.io.read_point_cloud(str(ply)).points)
    if len(pts) and float(np.ptp(pts[:, 0])) < 500.0:
        pts = pts * 1000.0
    z0 = float(g["floor_z"])
    h = float(g["ceiling_z"]) - z0
    print(f"\n{ply.name}: {len(faces)} GT-hyllynetupintaa")
    print(f"  {'#':>3} {'pituus':>7} " + " ".join(f"{'x' + str(r):>6}" for r in RATIOS))
    for i, f in enumerate(faces):
        a, b = np.asarray(f[0], float), np.asarray(f[1], float)
        w = {"id": f"shelf{i}", "axis": [list(a), list(b)], "z_min": z0,
             "height": h, "thickness": 120.0}
        lv = _levels(pts, w)
        cells = " ".join(f"{lv.get(r, 0):6d}" for r in RATIOS)
        print(f"  {i:>3} {np.linalg.norm(b - a) / 1000.0:6.1f} m {cells}")


def _store(d: Path) -> None:
    """Synteettinen keilattu myymala: hyllynetupinnat JA seinat samasta datasta.

    `_synth_store.py` antaa molemmat populaatiot samalla mittarilla ja samassa
    pilvessa, joten kynnys ei nojaa nelja naytetta vasten kuten ensimmaisessa
    mittauksessa.
    """
    P = np.load(d / "coord.npy").astype(np.float64)
    C = np.load(d / "class.npy")
    I = np.load(d / "instance.npy")
    g = json.loads((d / "gt.json").read_text(encoding="utf-8"))
    z0, h = float(g["floor_z"]), float(g["ceiling_z"]) - float(g["floor_z"])
    print(f"\n{d.name}: {len(g['shelf_faces'])} hyllynetupintaa")
    head = " ".join(f"x{r:>5}" for r in RATIOS)
    print(f"  {'#':>3} {'pituus':>7} {head}")
    face_lv = []
    for i, f in enumerate(g["shelf_faces"]):
        a, b = np.asarray(f[0], float), np.asarray(f[1], float)
        w = {"id": f"s{i}", "axis": [list(a), list(b)], "z_min": z0,
             "height": h, "thickness": 120.0}
        lv = _levels(P, w)
        face_lv.append(lv)
        cells = " ".join(f"{lv.get(r, 0):6d}" for r in RATIOS)
        print(f"  {i:>3} {np.linalg.norm(b - a) / 1000.0:6.1f} m {cells}")
    print(f"  {'-':>3} SEINAT")
    wall_lv = []
    for k in np.unique(I):
        m = I == k
        if m.sum() < 2000 or not np.isin(C[m], list(FACE)).any():
            continue
        Q = P[m]
        if float(np.linalg.norm(np.ptp(Q[:, :2], axis=0))) < 1500.0:
            continue
        lv = _levels(P, _wall_from_points(Q))
        wall_lv.append(lv)
        cells = " ".join(f"{lv.get(r, 0):6d}" for r in RATIOS)
        L = float(np.linalg.norm(np.ptp(Q[:, :2], axis=0))) / 1000.0
        print(f"  w{int(k):>2} {L:6.1f} m {cells}")
    for r in RATIOS:
        fv = sorted(x.get(r, 0) for x in face_lv)
        wv = sorted(x.get(r, 0) for x in wall_lv)
        print(f"  x{r}: hyllyt {fv}")
        print(f"        seinat {wv}")


def main() -> None:
    if len(sys.argv) > 1:
        _store(Path(sys.argv[1]))
        return
    for name in ("scene_07002", "scene_07001", "scene_07004"):
        _rohbau(ROOT / f"_rohbau/site_07/{name}", {})
    for tag in ("retail_s", "retail_l"):
        _retail(ROOT / f"_{tag}.ply", ROOT / f"_{tag}.ply.gt.json")


if __name__ == "__main__":
    main()

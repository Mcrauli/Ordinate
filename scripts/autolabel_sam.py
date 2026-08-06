"""Auto-labeler: E57-skanni → per-piste S3DIS-labelit (0-12) SAM + geometrialla.

SAM segmentoi jokaisen skannerikuvan puhtaisiin alueisiin; kukin alue saa luokan
sen takaisinprojisoitujen 3D-pisteiden GEOMETRIASTA (lattiataso→lattia, katto→katto,
seinätasolla→seinä, pilarilla→pilari, muu/edessä→clutter). Pisteille äänestetään
luokka kaikista kameroista jotka näkevät ne. Lisenssipuhdas (SAM Apache + oma data).

Aja:  python scripts/autolabel_sam.py <e57> <model.json> <out.npy>
Tuottaa Nx7 (xyz rgb label) + <out>.png (label-visualisointi validointiin).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sam_segment import MobileSAM  # noqa: E402

# S3DIS: 0 ceiling,1 floor,2 wall,4 column,12 clutter
CEIL, FLOOR, WALL, COL, CLUT = 0, 1, 2, 4, 12


def _quat_to_R(w, x, y, z):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _load_faces(e57_path: Path):
    import pye57
    f = pye57.E57(str(e57_path))
    root = f.root
    if "images2D" not in [c.elementName() for c in root]:
        return []
    im = root["images2D"]; faces = []
    for i in range(len(im)):
        el = im[i]
        try:
            ph = el["pinholeRepresentation"]; pose = el["pose"]
            rot, tr = pose["rotation"], pose["translation"]
            R = _quat_to_R(*[rot[k].value() for k in ("w", "x", "y", "z")])
            T = np.array([tr[k].value() for k in ("x", "y", "z")]) * 1000.0
            blob = ph["jpegImage"]; n = blob.byteCount(); buf = bytearray(n); blob.read(buf, 0, n)
            bgr = cv2.imdecode(np.frombuffer(bytes(buf), np.uint8), cv2.IMREAD_COLOR)
            intr = {k: ph[k].value() for k in ("focalLength", "pixelWidth", "pixelHeight",
                                               "principalPointX", "principalPointY",
                                               "imageWidth", "imageHeight")}
            faces.append((R, T, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), intr))
        except Exception:  # noqa: BLE001,PERF203
            continue
    return faces


def _region_class(pts3d, floor_z, ceil_z, model):
    """Alueen 3D-pisteet → S3DIS-luokka GEOMETRIASTA (mallista riippumaton).
    Seinä = ISO PYSTYTASO (PCA), ei mallinäheisyys → nappaa myös mallista puuttuvat
    väliseinät. None = epävarma → jätetään labeloimatta (ei myrkytetä treenidataa)."""
    if len(pts3d) < 40:
        return None
    z = pts3d[:, 2]; zmed = np.median(z)
    if abs(zmed - floor_z) < 300:
        return FLOOR
    if abs(zmed - ceil_z) < 350:
        return CEIL
    c = pts3d - pts3d.mean(0)
    cov = c.T @ c / len(c)
    evals, evecs = np.linalg.eigh(cov)          # nouseva
    normal = evecs[:, 0]
    planar = evals[0] < 0.02 * max(evals[2], 1e-9)      # ohut normaalin suunnassa
    vertical = abs(normal[2]) < 0.35                    # normaali vaakaan → pystytaso
    zext = float(z.max() - z.min()); spread = float(np.sqrt(evals[2]))
    xy = pts3d[:, :2]
    footprint = float(max(xy[:, 0].ptp(), xy[:, 1].ptp()))
    if planar and vertical and zext > 700 and spread > 500:
        return WALL
    # pilari: kapea pysty (pieni footprint, korkea)
    if footprint < 900 and zext > 1500:
        return COL
    # kompakti/ei-tasomainen mid-height objekti → kaluste
    if not (planar and vertical) and footprint < 3000:
        return CLUT
    return None                                          # epävarma → labeloimatta


def main():
    e57, mp, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    from scan2bim.core.geometry.loader import load_point_cloud
    cl = load_point_cloud(e57, e57_colors=True)
    P = np.asarray(cl.points, np.float32)
    RGB = (np.asarray(cl.colors) if cl.has_colors() else np.full((len(P), 3), 0.5)).astype(np.float32)
    step = max(1, len(P) // 2_000_000); P = P[::step]; RGB = RGB[::step]
    model = json.loads(mp.read_text(encoding="utf-8"))
    floor_z = min((s["elevation"] for s in model["slabs"] if s["slab_type"] == "floor"), default=float(np.percentile(P[:, 2], 1)))
    ceil_z = max((s["elevation"] for s in model["slabs"] if s["slab_type"] == "ceiling"), default=float(np.percentile(P[:, 2], 99)))
    faces = _load_faces(e57)
    print(f"pisteitä {len(P)} · kuvia {len(faces)} · floor {floor_z:.0f} ceil {ceil_z:.0f}", flush=True)
    sam = MobileSAM()
    votes = defaultdict(lambda: defaultdict(int))   # point_idx -> {class: count}
    for fi, (R, T, img, intr) in enumerate(faces):
        Wpx, Hpx = intr["imageWidth"], intr["imageHeight"]
        dc = (P - T) @ R; z = dc[:, 2]
        front = z > 200
        u = intr["principalPointX"] + intr["focalLength"] * dc[:, 0] / (z * intr["pixelWidth"])
        v = intr["principalPointY"] + intr["focalLength"] * dc[:, 1] / (z * intr["pixelHeight"])
        inim = front & (u >= 0) & (u < Wpx) & (v >= 0) & (v < Hpx)
        if inim.sum() < 500:
            continue
        # z-puskuri: piste näkyvä jos ~lähin omalla pikselillään (kart. 4px ruutu)
        idx = np.where(inim)[0]
        pu = (u[idx] / 4).astype(int); pv = (v[idx] / 4).astype(int); zz = z[idx]
        key = pv * (Wpx // 4 + 1) + pu
        order = np.argsort(zz); nearest = {}
        for j in order:
            k = key[j]
            if k not in nearest:
                nearest[k] = idx[j]
        vis_idx = np.array(list(nearest.values()))
        # SAM-alueet (1024-kehys → skaalaa kuvakehykseen)
        masks = sam.segment_everything(img, grid=12)
        if not masks:
            continue
        sc = Wpx / 1024.0
        # rakenna region-id-kartta kuvakehyksessä
        regmap = np.full((Hpx, Wpx), -1, np.int32)
        for ri, mk in enumerate(masks):
            mkf = cv2.resize(mk.astype(np.uint8), (Wpx, Hpx), interpolation=cv2.INTER_NEAREST) > 0
            regmap[mkf] = ri
        uu = u[vis_idx].astype(int); vv = v[vis_idx].astype(int)
        rid = regmap[np.clip(vv, 0, Hpx - 1), np.clip(uu, 0, Wpx - 1)]
        for ri in range(len(masks)):
            sel = vis_idx[rid == ri]
            if len(sel) < 30:
                continue
            cls = _region_class(P[sel], floor_z, ceil_z, model)
            if cls is None:
                continue
            for s in sel:
                votes[int(s)][cls] += 1
        print(f"  kuva {fi+1}/{len(faces)}: {len(masks)} aluetta, {len(vis_idx)} näkyvää", flush=True)
    # äänestys → label; äänestämättömät geometrialla (fallback)
    lab = np.full(len(P), -1, np.int8)
    for pi, vd in votes.items():
        lab[pi] = max(vd, key=vd.get)
    # fallback VAIN selkeälle lattia/katolle; muut epävarmat JÄTETÄÄN labeloimatta
    # (-1) → ei myrkytetä treenidataa (mallista puuttuva seinä ei saa mennä clutteriksi)
    z = P[:, 2]
    unl = lab < 0
    lab[unl & (np.abs(z - floor_z) < 200)] = FLOOR
    lab[unl & (np.abs(z - ceil_z) < 250)] = CEIL
    counts = {c: int((lab == c).sum()) for c in sorted(set(lab.tolist()))}
    names = {-1: "EI-LAB", 0: "ceil", 1: "floor", 2: "wall", 4: "col", 12: "clut"}
    print("LABELIT:", {names.get(k, k): f"{100*v/len(P):.1f}%" for k, v in counts.items()}, flush=True)
    # TREENIDATA = vain varmat (label>=0)
    keep = lab >= 0
    np.save(out, np.column_stack([P[keep], RGB[keep], lab[keep].astype(np.float32)]))
    print(f"treenipisteitä (label>=0): {keep.sum()} / {len(P)}", flush=True)
    # visualisointi keskikorkeus
    cmap = {0: (0.5, 0.5, 1), 1: (0.6, 0.4, 0.2), 2: (0, 0.8, 1), 4: (1, 0.8, 0), 12: (1, 0.2, 0.2)}
    col = np.array([cmap.get(int(x), (0.5, 0.5, 0.5)) for x in lab])
    zlo, zhi = np.percentile(z, [2, 98]); band = (z > zlo + 0.3 * (zhi - zlo)) & (z < zlo + 0.6 * (zhi - zlo))
    sub = np.where(band)[0]; sub = sub[:: max(1, len(sub) // 400000)]
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 14))
    ax.scatter(P[sub, 0], P[sub, 1], s=0.7, c=col[sub], linewidths=0)
    ax.set_aspect("equal"); ax.set_title("SAM AUTO-LABEL: syaani=seinä keltainen=pilari PUNAINEN=clutter. Ovatko kalusteet punaisia, seinät syaaneja?")
    plt.savefig(str(out) + ".png", dpi=90); print("saved", out, "+ .png", flush=True)


if __name__ == "__main__":
    main()

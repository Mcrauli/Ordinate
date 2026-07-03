"""Batch-validointi SpatialLM-GT:ta vasten: aja kansion PLY:t joilla on .txt-annotaatio.

    python data/_spatiallm_qa.py <kansio jossa scene_*.ply + scene_*.txt>

Mittarit: seinien lateraalivirhe (GT-keskipiste -> det-akselilinja), kulmavirhe,
osumat/GT-seinat (vain scenen pistedatan kattamat GT-seinat lasketaan).
HUOM: GT-viivat ovat seinapintoja/keskilinjoja — ~puolikas seinapaksuus (~100mm)
lateraalimediaanissa on konventioero, ei mittausvirhe."""
import math, re, sys, tempfile, time
import numpy as np, open3d as o3d
from pathlib import Path
from scan2bim.core.pipeline import Pipeline, PipelineConfig

DIR = Path(sys.argv[1])
OUT = Path(tempfile.gettempdir()) / "_spatiallm_qa"

def parse_gt(txt):
    walls, doors, wins = [], 0, 0
    for line in txt.splitlines():
        m = re.match(r"wall_\d+\s*=\s*Wall\(([^)]+)\)", line)
        if m:
            v = [float(x) for x in m.group(1).split(",")]
            walls.append((np.array([v[0], v[1]]) * 1000, np.array([v[3], v[4]]) * 1000))
        doors += bool(re.match(r"door_\d+\s*=", line))
        wins += bool(re.match(r"window_\d+\s*=", line))
    return walls, doors, wins

def lat_dist_and_ang(gm, ga, walls):
    best = None
    for w in walls:
        p0 = np.array(w.axis[0]); p1 = np.array(w.axis[1])
        d = p1 - p0; L = float(np.linalg.norm(d))
        if L < 1: continue
        u = d / L
        da = math.degrees(math.atan2(u[1], u[0])) % 180
        dang = min(abs(ga - da), 180 - abs(ga - da))
        if dang > 15: continue
        t = float((gm - p0) @ u)
        if t < -500 or t > L + 500: continue
        lat = abs(float((gm - p0) @ np.array([-u[1], u[0]])))
        if best is None or lat < best[0]:
            best = (lat, dang)
    return best

all_lat, all_ang = [], []
for ply in sorted(DIR.glob("*.ply")):
    gt_file = ply.with_suffix(".txt")
    if not gt_file.exists(): continue
    gt_walls, gt_d, gt_w = parse_gt(gt_file.read_text(encoding="utf-8", errors="ignore"))
    pc = o3d.io.read_point_cloud(str(ply))
    pts = np.asarray(pc.points)
    if np.ptp(pts[:, 0]) < 100: pts = pts * 1000.0
    cfg = PipelineConfig(auto_voxel=True, detector="contour", export_ifc=False,
                         export_dxf=False, export_qa=False, semantic_filter_mode="pointnet")
    t0 = time.time()
    try:
        m = Pipeline(cfg).run_floors([ply], OUT / ply.stem)[0]
    except Exception as e:
        print(f"{ply.stem}: VIRHE {e}")
        continue
    lats, angs, matched, covered = [], [], 0, 0
    for (a, b) in gt_walls:
        gm = (a + b) / 2.0
        ga = math.degrees(math.atan2(*(b - a)[::-1])) % 180
        # GT-seina "katettu" jos pilvessa on pisteita sen lahella
        d2 = np.min(np.linalg.norm(pts[:, :2] - gm, axis=1)) if len(pts) else 1e9
        if d2 > 800: continue
        covered += 1
        r = lat_dist_and_ang(gm, ga, m.walls)
        if r and r[0] < 600:
            matched += 1; lats.append(r[0]); angs.append(r[1])
    nd = sum(1 for o in (m.openings or []) if str(o.opening_type) == "door")
    nw = len(m.openings or []) - nd
    med = np.median(lats) if lats else float("nan")
    mang = np.median(angs) if angs else float("nan")
    print(f"{ply.stem}: seinia det={len(m.walls)} GT(katettu)={covered} osuma={matched} "
          f"lat-med={med:.0f}mm ang-med={mang:.1f} deg aukot d{nd}/w{nw} (GT d{gt_d}/w{gt_w}) "
          f"[{time.time()-t0:.0f}s]", flush=True)
    all_lat += lats; all_ang += angs

if all_lat:
    print(f"\nYHTEENSA: n={len(all_lat)} lat mediaani={np.median(all_lat):.0f}mm "
          f"p90={np.percentile(all_lat, 90):.0f}mm ang mediaani={np.median(all_ang):.2f} deg")

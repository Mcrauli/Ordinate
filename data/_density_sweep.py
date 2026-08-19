"""Kuinka harvalla skannilla putki vielä toimii — mitattuna, ei arvattuna.

Kynnykset on viritetty tiheillä keilauksilla ja moni niistä on ABSOLUUTTINEN
pistemäärä (`_MIN_INLIERS` 300, `_MIN_CLUSTER_PTS` 120, `_MIN_PTS_BASELINE` 30).
Harvemmalla skannerilla aito seinä putoaa kynnyksen alle eikä mikään kerro
siitä. Perjantaina tulee tuntemattomia skanneja: on tiedettävä ETUKÄTEEN missä
tiheydessä laatu romahtaa.

Tämä harventaa saman pilven voxelilla useaan tiheyteen, ajaa KOKO putken
jokaisella ja mittaa seinä- ja palkki-instanssit samaa GT:tä vasten. Ero on
puhtaasti tiheyden — kaikki muu on vakio.

Ajo: .venv/Scripts/python.exe data/_density_sweep.py [scene] [voxel_mm ...]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import DATA, OUTPUT  # noqa: E402

HERE = Path(__file__).resolve().parent
PY = str(Path(sys.executable))
_SITE = "site_07"


def _spacing(pts: np.ndarray) -> float:
    from scipy.spatial import cKDTree
    n = min(len(pts), 20_000)
    idx = np.linspace(0, len(pts) - 1, n).astype(np.int64)
    d, _ = cKDTree(pts).query(pts[idx], k=2)
    d = d[:, 1]
    return float(np.median(d[d > 0.0]))


def _qa(script: str, model: Path, scene_dir: Path) -> str:
    return subprocess.run(
        [PY, str(HERE / script), str(model),
         str(scene_dir / "coord.npy"), str(scene_dir / "class.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def main() -> None:
    scene = sys.argv[1] if len(sys.argv) > 1 else "scene_07000"
    voxels = [float(v) for v in sys.argv[2:]] or [0.0, 10.0, 20.0, 40.0, 80.0]
    scene_dir = Path(str(DATA / "_rohbau" / _SITE / scene))
    src = scene_dir / "cloud.ply"
    if not src.exists():
        P = np.load(scene_dir / "coord.npy").astype(np.float64)
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(P)
        o3d.io.write_point_cloud(str(src), pc)
    base = o3d.io.read_point_cloud(str(src))

    rows = []
    for v in voxels:
        # cloud.ply on metreissä; voxel annetaan millimetreinä.
        pc = base if v <= 0.0 else base.voxel_down_sample(v / 1000.0)
        pts = np.asarray(pc.points)
        tag = f"_dens_{scene}_{int(v):03d}"
        ply = Path(str(DATA / f"{tag}.ply"))
        o3d.io.write_point_cloud(str(ply), pc)
        out = Path(str(OUTPUT / tag))
        print(f"\n===== voxel {v:.0f} mm  {len(pts):,} pistettä =====", flush=True)
        r = subprocess.run([PY, str(HERE / "_run_one.py"), str(ply), str(out)])
        model = out / "floor_00" / "model.json"
        if not model.exists():
            model = out / "model.json"
        if r.returncode != 0 or not model.exists():
            rows.append((v, len(pts), _spacing(pts) * 1000.0, "kaatui", "", "", ""))
            continue
        w = _qa("_wall_inst_qa.py", model, scene_dir)
        b = _qa("_beam_qa.py", model, scene_dir)
        rows.append((v, len(pts), _spacing(pts) * 1000.0,
                     _num(r"JALANJALJEN SISALLA \d+/\d+ = ([\d.]+)", w),
                     _num(r"INSTANSSIKATTAVUUS \d+/\d+ = ([\d.]+)", w),
                     _num(r"INSTANSSIKATTAVUUS \d+/\d+ = ([\d.]+)", b),
                     _num(r"TARKKUUS.*?([\d.]+)", b)))

    print("")
    print(f"{'voxel':>6s} {'pisteitä':>12s} {'pisteväli':>10s} {'seinä/jalanj':>12s} "
          f"{'seinä/kaikki':>12s} {'palkki':>7s} {'palkki-tark':>11s}")
    for v, n, sp, a, c, bb, bp in rows:
        print(f"{v:6.0f} {n:12,d} {sp:9.1f}mm {a:>12s} {c:>12s} {bb:>7s} {bp:>11s}")
    print("")
    print("Romahduskohta = ensimmäinen rivi jolla kattavuus putoaa selvästi. "
          "Sen yläpuolella olevaa pisteväliä ei saa luvata toimivaksi.")


if __name__ == "__main__":
    main()

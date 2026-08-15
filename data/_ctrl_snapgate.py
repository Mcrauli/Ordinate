"""Kontrolli: mitä napsautusportin levennys (`_SNAP_MAX_SUP`) tekee malliin?

Ajaa Rohbaun kahdesti — kerran vanhalla ehdolla (vain `support == 0`
napsautetaan), kerran nykyisellä — ja vertaa seiniä sekä GT-lukuja.

Ajo: .venv/Scripts/python.exe data/_ctrl_snapgate.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scan2bim.core.semantics.wall_semantics as WS  # noqa: E402
from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402
from _paths import DATA, OUTPUT  # noqa: E402

SCENE = Path(str(DATA / "_rohbau/site_07/scene_07000"))


def run(tag: str, gate: float):
    WS._SNAP_MAX_SUP = gate
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False,
                         semantic_filter_mode="pointnet")
    out = Path(str(OUTPUT / f"_ctrlsnap_{tag}"))
    Pipeline(cfg).run_floors([SCENE / "cloud.ply"], out)
    return out / "floor_00" / "model.json"


def qa(mj: Path) -> str:
    r = subprocess.run(
        [sys.executable, "data/_rohbau_qa.py", str(mj),
         str(SCENE / "coord.npy"), str(SCENE / "class.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return "\n".join(l for l in r.stdout.splitlines()
                     if "KATTAVUUS" in l or "TARKKUUS" in l or "ONGELMASEINIA" in l)


def main() -> None:
    for tag, gate in (("old", 1e-9), ("new", 0.50)):
        mj = run(tag, gate)
        m = json.loads(mj.read_text(encoding="utf-8"))
        print(f"\n== portti {gate:g}: {len(m['walls'])} seinää")
        for w in sorted(m["walls"], key=lambda x: x["id"]):
            a = np.array(w["axis"][0], float)
            b = np.array(w["axis"][1], float)
            print(f"   {w['id']:14s} L={np.linalg.norm(b-a)/1000:5.1f}m "
                  f"tuki={w.get('support')} akseli=({a[0]:.0f},{a[1]:.0f})")
        print(qa(mj))


if __name__ == "__main__":
    main()

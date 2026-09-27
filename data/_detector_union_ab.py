"""Mita jos ehdokkaita EI valita vaan yhdistetaan ja portit tuomitsevat?

Putki ajaa jo kaikki kolme detektoria valintaa varten ja heittaa kaksi pois.
Valinta on mitatusti vaara Rohbaussa (+0.063 instanssikattavuutta poydalla,
ks. AGENTS.md) eika yksikaan GT-vapaa mittari osaa asettaa detektoreita
jarjestykseen — kolme kumottu.

Unioni ohittaa koko kysymyksen: jokainen ehdokas paasee ketjuun ja ketju
paattaa. Perustelu on sama jolla jaannosseinahaku kytkettiin takaisin
30.8.2026: silloin ketjuun oli tullut kolme mitattua porttia (semanttinen
enemmisto, kontrasti, tasomaisuus) jotka osaavat tuomita huonon ehdokkaan.
Nyt niita on nelja (+ suunta).

RISKI on tarkkuus, ja se on juuri se mita tama mittaa. Jos portit eivat
tuomitse, tarkkuus romahtaa kuten jaannosseinahaussa 18.8. (0.924 -> 0.515).

Kaytto: _detector_union_ab.py <scene_dir> <out_dir>
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

NAMES = ("contour", "histogram", "normals")


def _inst(model: Path, scene: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(HERE / "_wall_inst_qa.py"), str(model),
         str(scene / "coord.npy"), str(scene / "class.npy"),
         str(scene / "instance.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = [l.strip() for l in r.stdout.splitlines()
           if "INSTANSSIKATTAVUUS" in l or "JALANJALJEN" in l]
    return " | ".join(out)


def _gt(model: Path, scene: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(HERE / "_rohbau_qa.py"), str(model),
         str(scene / "coord.npy"), str(scene / "class.npy")],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for l in r.stdout.splitlines():
        if l.startswith(("KATTAVUUS", "TARKKUUS")):
            out.append(" ".join(l.split()))
    return " | ".join(out)


def _nogt(model: Path, cloud: Path) -> str:
    r = subprocess.run(
        [sys.executable, str(HERE / "_wall_coverage_nogt.py"), str(model), str(cloud)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = [" ".join(l.split()) for l in r.stdout.splitlines()
           if l.startswith(("KATTAVUUS", "TARKKUUS"))]
    return " | ".join(out)


def main(scene_dir: str, out_root: str, only: str = "") -> None:
    """`scene_dir` voi olla Rohbau-hakemisto (GT) tai suoraan .ply (ei GT)."""
    from ordinate.core import pipeline as PL
    from ordinate.core.segmentation.base import DetectorRegistry

    arg = Path(scene_dir)
    if arg.suffix.lower() == ".ply":
        scene, cloud = None, arg
    else:
        scene, cloud = arg, arg / "cloud.ply"

    use = tuple(only.split(",")) if only else None

    def _union(self, cloud, names):
        """Aja ehdokkaat taydella pilvella ja yhdista seinat."""
        if use:
            names = [n for n in names if n in use] or list(names[:1])
        base = None
        walls = []
        for n in names:
            det = DetectorRegistry.get(n)()
            if self._sem_labels is not None and hasattr(det, "semantic_labels"):
                det.semantic_labels = self._sem_labels
            m = det.detect(cloud)
            self._progress(f"    {n}: {len(m.walls)} seinaa")
            for i, w in enumerate(m.walls):
                walls.append(w.model_copy(update={"id": f"{n[:4]}_{i:03d}"}))
            if base is None or len(m.walls) > len(base.walls):
                base = m
        self._progress(f"  UNIONI: {len(walls)} seinaa")
        return base.model_copy(update={"walls": walls}), "union"

    PL.Pipeline._best_detector = _union
    cfg = PL.PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                            export_dxf=False, export_qa=False,
                            semantic_filter_mode="pointnet")
    out = Path(out_root)
    m = PL.Pipeline(cfg, progress=lambda s: None).run_floors([cloud], out)[0]
    mj = out / "floor_00" / "model.json"
    print(f"union     seinia {len(m.walls):3d}")
    print(f"          GT-vapaa: {_nogt(mj, cloud)}")
    if scene is not None:
        print(f"          {_gt(mj, scene)}")
        print(f"          {_inst(mj, scene)}")
    sys.stdout.flush()


if __name__ == "__main__":
    main(*sys.argv[1:])

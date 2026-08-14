"""Kuvaohjattu aukkodetektio OIKEALLA kuvallisella E57:llä: vanha vs uusi koodi.

Ajaa putken kerran (seinät + pilvi), ja kutsuu sitten SEKÄ nykyistä ETTÄ
git-historiasta poimittua vanhaa `detect_image_openings`ia samoilla syötteillä.
Näin refaktoroinnin neutraalius todistetaan oikealla datalla ilman kahta ajoa.

Ajo:
    .venv/Scripts/python.exe data/_img_openings_qa.py <scan.e57> [vanha_moduuli.py]
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scan2bim.core.pipeline import Pipeline, PipelineConfig  # noqa: E402
from scan2bim.core.segmentation import image_openings as new_io  # noqa: E402


def _key(ops):
    return sorted(
        (o.wall_id, o.opening_type, round(o.position_along, 3), round(o.width, 3),
         round(o.sill_height, 3), round(o.opening_height, 3))
        for o in ops
    )


def main() -> None:
    scan = Path(sys.argv[1]).expanduser()
    old_path = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else None

    out = Path("data/output/_imgqa")
    cfg = PipelineConfig(detector="contour", auto_voxel=True, export_ifc=False,
                         export_dxf=False, export_qa=False,
                         semantic_filter_mode="pointnet")
    pipe = Pipeline(cfg)
    t = time.time()
    models = pipe.run_floors([scan], out)
    print(f"\nputki {time.time() - t:.0f} s, {len(models)} kerrosta")
    if not models:
        print("Ei kerroksia — skanni ei ole sisätila oikeassa mittakaavassa?\n"
              "  (parking-lot-updated.e57 on laajuudeltaan vain 418x498x112 mm.)\n"
              "  Tarvitaan kuvallinen SISÄTILA-E57, esim. Matterport-aula.")
        return

    model = models[0]
    img_ops = [o for o in model.openings if o.source.notes == "image-seethru"]
    geo_ops = [o for o in model.openings if o.source.notes != "image-seethru"]
    print(f"seiniä {len(model.walls)}, aukkoja {len(model.openings)} "
          f"(geometria {len(geo_ops)}, KUVAOHJATTU {len(img_ops)})")
    for o in img_ops:
        print(f"  {o.id} {o.opening_type} {o.wall_id} "
              f"L={o.position_along:.0f} w={o.width:.0f} h={o.opening_height:.0f} "
              f"sill={o.sill_height:.0f}")

    if old_path is None:
        return

    # Sama pilvi kuin detektiossa, jotta vertailu on aito.
    from scan2bim.core.geometry.loader import load_point_cloud
    pts = np.asarray(load_point_cloud(scan).points)

    t = time.time()
    a = _key(new_io.detect_image_openings(model.walls, scan, pts))
    t_new = time.time() - t

    spec = importlib.util.spec_from_file_location("old_io", str(old_path))
    old_io = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_io)
    t = time.time()
    b = _key(old_io.detect_image_openings(model.walls, scan, pts))
    t_old = time.time() - t

    print(f"\nuusi  {len(a)} aukkoa  {t_new:6.2f} s")
    print(f"vanha {len(b)} aukkoa  {t_old:6.2f} s")
    print(f"TÄYSIN SAMAT: {a == b}")
    if a != b:
        for x in a:
            if x not in b:
                print("  vain uudessa:", x)
        for x in b:
            if x not in a:
                print("  vain vanhassa:", x)


if __name__ == "__main__":
    main()

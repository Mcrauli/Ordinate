"""Yleistyvyysmittaus: KAIKKI Rohbau-scenet, ei vain se johon on viritetty.

Kynnykset ja saannot on valittu `scene_07000`:sta. Se ei kerro toimiiko putki
millaan muulla skannilla — ja juuri se on vaatimus. Tama ajaa jokaisen scenen
erikseen (asemat ovat huonosti rekisteroityja keskenaan) ja tulostaa
kattavuuden, tarkkuuden ja ongelmaseinat rinnakkain.

Ajo: .venv/Scripts/python.exe data/_rohbau_all.py [site] [scene ...]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import DATA, OUTPUT  # noqa: E402

HERE = Path(__file__).resolve().parent
PY = str(Path(sys.executable))


def main() -> None:
    site = sys.argv[1] if len(sys.argv) > 1 else "site_07"
    root = Path(str(DATA / "_rohbau" / site))
    scenes = sys.argv[2:] or [p.name for p in sorted(root.iterdir()) if p.is_dir()]

    rows = []
    for sc in scenes:
        print(f"\n===== {sc} =====", flush=True)
        subprocess.run([PY, str(HERE / "_run_rohbau.py"), site, sc], check=True)
        model = Path(str(OUTPUT / f"_rohbau_{site}_{sc}" / "floor_00" / "model.json"))
        if not model.exists():
            rows.append((sc, None, None, "ei mallia"))
            continue
        out = subprocess.run(
            [PY, str(HERE / "_rohbau_qa.py"), str(model),
             str(root / sc / "coord.npy"), str(root / sc / "class.npy")],
            capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        cov = re.search(r"KATTAVUUS.*?([\d.]+)", out)
        pre = re.search(r"TARKKUUS.*?([\d.]+)", out)
        bad = re.search(r"ONGELMASEINIA (\d+)(.*)", out)
        n2nd = out.count("second_face")
        rows.append((sc, cov and cov.group(1), pre and pre.group(1),
                     (bad.group(1) + bad.group(2).strip()) if bad else "?", n2nd))

    print(f"\n{'scene':14s} {'kattavuus':>10s} {'tarkkuus':>9s} {'katve':>6s}  ongelmat")
    for sc, cov, pre, bad, *rest in rows:
        n2 = rest[0] if rest else 0
        print(f"{sc:14s} {cov or '-':>10s} {pre or '-':>9s} {n2:6d}  {bad}")


if __name__ == "__main__":
    main()

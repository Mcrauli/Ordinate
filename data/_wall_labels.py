"""Kirjaa kontaktiarkilta luetut labelit: mitka seinat EIVAT ole seinia.

Kaytto:
  _wall_labels.py <arkkihakemisto> "3 7 12 40-45"      # naa ovat VAARIA
  _wall_labels.py <arkkihakemisto> --file vaarat.txt

Tulos: <arkkihakemisto>/labels.json  { "wall_id": 0|1, ... } jossa 1 = aito.
Kaikki numerot joita EI mainita ovat aitoja — se on nopein tapa, koska
valeseinia on tyypillisesti vahemman.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _parse(spec: str) -> set[int]:
    out: set[int] = set()
    for tok in spec.replace(",", " ").split():
        if "-" in tok[1:]:
            a, b = tok.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif tok.strip():
            out.add(int(tok))
    return out


def main() -> None:
    d = Path(sys.argv[1])
    if "--file" in sys.argv:
        spec = Path(sys.argv[sys.argv.index("--file") + 1]).read_text(encoding="utf-8")
    else:
        spec = " ".join(a for a in sys.argv[2:] if not a.startswith("--"))
    bad = _parse(spec)
    index = json.loads((d / "walls.json").read_text(encoding="utf-8"))
    labels = {w["id"]: (0 if w["i"] in bad else 1) for w in index}
    unknown = sorted(i for i in bad if i >= len(index))
    (d / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    n_bad = sum(1 for v in labels.values() if v == 0)
    print(f"{len(labels)} seinaa: {len(labels) - n_bad} aitoa, {n_bad} vaaraa "
          f"-> {d / 'labels.json'}")
    if unknown:
        print(f"  VAROITUS: numerot {unknown} eivat ole indeksissa")


if __name__ == "__main__":
    main()

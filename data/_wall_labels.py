"""Kirjaa kontaktiarkilta luetut labelit: mitka seinat EIVAT ole seinia.

Kaytto:
  _wall_labels.py <arkkihakemisto> "3 7 12 40-45"      # naa ovat VAARIA
  _wall_labels.py <arkkihakemisto> "3 7" --unsure "9 14"  # 9 ja 14 jaa auki
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
    # EPAVARMAT jatetaan kokonaan pois labeleista. Pakotettu arvaus on
    # huonompi kuin puuttuva label: se opettaa mallille vaaran asian ja
    # vaaristaa mitatun tarkkuuden. Rajatapauksen saa ja pitaa jattaa auki.
    unsure = _parse(sys.argv[sys.argv.index("--unsure") + 1]) if "--unsure" in sys.argv else set()
    index = json.loads((d / "walls.json").read_text(encoding="utf-8"))
    # Avain on INDEKSI eika id: mallin `Wall.id` EI ole uniikki (kellarissa
    # kahdeksan `wall_res_*`-tunnistetta esiintyy kahdesti), joten id:lla
    # avainnettu label osuisi kahteen eri seinaan ja mittaus olisi vaarin.
    labels = {str(w["i"]): (0 if w["i"] in bad else 1)
              for w in index if w["i"] not in unsure}
    unknown = sorted(i for i in bad | unsure if i >= len(index))
    (d / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    n_bad = sum(1 for v in labels.values() if v == 0)
    print(f"{len(index)} seinaa: {len(labels) - n_bad} aitoa, {n_bad} vaaraa, "
          f"{len(unsure)} epavarmaa (jatetty pois) -> {d / 'labels.json'}")
    if unknown:
        print(f"  VAROITUS: numerot {unknown} eivat ole indeksissa")


if __name__ == "__main__":
    main()

"""Yksi taulukko: aineisto x elementtityyppi x (kattavuus, tarkkuus).

Mittarit olivat neljassa eri skriptissa ja niiden luvut vertailtiin muistista.
Tama ajaa ne kaikki valmiita `model.json`-tuloksia vasten ja tulostaa yhden
matriisin. EI aja putkea: mallin ika naytetaan sarakkeessa, jotta vanhentunut
tulos ei mene uutena luvusta lapi.

Ajo: _qa_all.py [--only rohbau|retail]
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
PY = sys.executable
DATA = ROOT / "data"


def _run(script: str, *args: str) -> str:
    r = subprocess.run([PY, str(HERE / script), *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout + r.stderr


def _num(pat: str, text: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def _model(out_dir: Path) -> Path:
    """Yksitiedostoajo kirjoittaa `model.json`:n juureen, monikerros floor_00:aan."""
    a = out_dir / "floor_00" / "model.json"
    b = out_dir / "model.json"
    if a.exists() and b.exists():
        return a if a.stat().st_mtime >= b.stat().st_mtime else b
    return a if a.exists() else b


def _age(p: Path) -> str:
    if not p.exists():
        return "-"
    d = _dt.datetime.now() - _dt.datetime.fromtimestamp(p.stat().st_mtime)
    return f"{d.days}vrk" if d.days else f"{int(d.total_seconds() // 3600)}h"


def rohbau(rows: list) -> None:
    site = DATA / "_rohbau" / "site_07"
    if not site.exists():
        return
    for sc in sorted(p.name for p in site.iterdir() if p.is_dir()):
        mj = _model(DATA / "output" / f"_rohbau_site_07_{sc}")
        if not mj.exists():
            rows.append((sc, "-", "ei mallia", "", "", ""))
            continue
        coord = str(site / sc / "coord.npy")
        cls = str(site / sc / "class.npy")
        w = _run("_rohbau_qa.py", str(mj), coord, cls)
        b = _run("_beam_qa.py", str(mj), coord, cls)
        c = _run("_column_qa.py", str(mj), coord, cls)
        o = _run("_opening_qa.py", str(mj), coord, cls)
        rows.append((sc, _age(mj), "seina",
                     _num(r"KATTAVUUS.*?([\d.]+)", w), _num(r"TARKKUUS.*?([\d.]+)", w),
                     f"ongelmaseinia {_num(r'ONGELMASEINIA (\d+)', w)}"))
        rows.append(("", "", "palkki",
                     _num(r"INSTANSSIKATTAVUUS \d+/\d+ = ([\d.]+)", b),
                     _num(r"TARKKUUS.*?([\d.]+)", b),
                     _num(r"(INSTANSSIKATTAVUUS \d+/\d+)", b)))
        rows.append(("", "", "pilari",
                     _num(r"INSTANSSIKATTAVUUS \d+/\d+ = ([\d.]+)", c),
                     _num(r"TARKKUUS.*?([\d.]+)", c),
                     "pilasterit seinassa"))
        rows.append(("", "", "aukko",
                     _num(r"KATTAVUUS  GT-aukoista mallissa: \d+/\d+ = ([\d.]+)", o),
                     _num(r"TARKKUUS   mallin aukoista GT-aukolla: \d+/\d+ = ([\d.]+)", o),
                     _num(r"(GT-aukoista mallissa: \d+/\d+)", o)))


def retail(rows: list) -> None:
    for tag in ("_retail_s", "_retail_l"):
        gt = DATA / f"{tag}.ply.gt.json"
        mj = _model(DATA / "output" / f"_2nd{tag}")
        if not (gt.exists() and mj.exists()):
            continue
        b = _run("_beam_synth_qa.py", str(mj), str(gt))
        g = json.loads(gt.read_text(encoding="utf-8"))
        m = json.loads(mj.read_text(encoding="utf-8"))
        rows.append((tag, _age(mj), "palkki",
                     _num(r"KATTAVUUS.*?([\d.]+)", b), _num(r"TARKKUUS.*?([\d.]+)", b),
                     f"harhapalkkeja {_num(r'HARHAPALKKEJA (\d+)', b)}"))
        rows.append(("", "", "pilari", "-", "-",
                     f"{len(m.get('columns', []))}/{len(g.get('columns', []))} kpl"))
        rows.append(("", "", "seina", "-", "-",
                     f"{len(m.get('walls', []))}/{len(g.get('walls', []))} kpl"))


def main() -> None:
    only = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--only" else None
    rows: list = []
    if only in (None, "rohbau"):
        rohbau(rows)
    if only in (None, "retail"):
        retail(rows)
    print(f"{'aineisto':14s} {'ika':>5s} {'tyyppi':8s} {'kattavuus':>9s} "
          f"{'tarkkuus':>8s}  huomio")
    for r in rows:
        print(f"{r[0]:14s} {r[1]:>5s} {r[2]:8s} {r[3]:>9s} {r[4]:>8s}  {r[5]}")


if __name__ == "__main__":
    main()

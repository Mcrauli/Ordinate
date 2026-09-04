"""Mika detektori olisi valittu TOISELLA saannolla — ilman uutta ajoa.

`diagnostics.txt` kirjaa jokaisesta ehdokkaasta kattavuuden, tarkkuuden ja
F1:n seka valitun. Valintasaanto on puhdasta aritmetiikkaa naiden luvuista,
joten vaihtoehtoiset saannot voi toistaa suoraan lokista. Detektorien
ajaminen uudelleen maksaa minuutteja per aineisto eika toisi yhtaan uutta
lukua.

Kaytto: _choice_rule_replay.py [matriisihakemisto]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARGIN_ONLY = {"normals"}

_CAND = re.compile(
    r"^\[[^\]]*\]\s+(\w+): F1 ([\d.]+) \(kattavuus ([\d.]+), tarkkuus ([\d.]+), (\d+) sein")
_PICK = re.compile(r"^\[[^\]]*\]\s+valittu (\w+)")


def _parse(diag: Path) -> tuple[dict[str, tuple[float, float, float]], str | None]:
    cands: dict[str, tuple[float, float, float]] = {}
    pick = None
    for line in diag.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _CAND.match(line)
        if m:
            cands[m.group(1)] = (float(m.group(3)), float(m.group(4)), float(m.group(2)))
        p = _PICK.match(line)
        if p:
            pick = p.group(1)
    return cands, pick


def _choose(cands: dict[str, tuple[float, float, float]], key: int, margin: float,
            margin_key: int) -> str:
    """key: 0=kattavuus, 2=F1 — kumpaa maksimoidaan ja mihin marginaali vertaa."""
    order = list(cands)
    best = max(order, key=lambda n: (cands[n][key], -order.index(n)))
    settled = {n: cands[n][2] for n in order if n not in MARGIN_ONLY}
    if settled and best in MARGIN_ONLY:
        ref = max(settled, key=lambda n: settled[n])
        if cands[best][margin_key] < margin * settled[ref]:
            return ref
    return best


def main(root: str = "data/output/_matrix") -> None:
    base = Path(root)
    if not base.is_absolute():
        base = ROOT / base
    rows = []
    for d in sorted(base.iterdir()):
        diag = d / "diagnostics.txt"
        if not diag.exists():
            continue
        cands, pick = _parse(diag)
        if len(cands) < 2 or pick is None:
            continue
        rows.append((d.name, cands, pick))

    print(f"{'aineisto':14s} {'lokissa':10s} {'nyt':10s} {'F1 m=3.0':10s} "
          f"{'F1 m=1.5':10s} {'F1 ei marg':10s}")
    for name, c, pick in rows:
        now = _choose(c, 0, 3.0, 0)          # nykyinen: argmax kattavuus, marginaali sekayksikolla
        f1_3 = _choose(c, 2, 3.0, 2)
        f1_15 = _choose(c, 2, 1.5, 2)
        f1_no = _choose(c, 2, 0.0, 2)
        flag = "" if now == pick else "  <-- EI TASMAA LOKIIN"
        print(f"{name:14s} {pick:10s} {now:10s} {f1_3:10s} {f1_15:10s} {f1_no:10s}{flag}")

    print()
    print("Marginaali-ikkuna jossa F1-saanto toistaa jokaisen lokin valinnan:")
    lo, hi = 0.0, float("inf")
    for name, c, pick in rows:
        settled = {n: c[n][2] for n in c if n not in MARGIN_ONLY}
        if not settled:
            continue
        order = list(c)
        best = max(order, key=lambda n: (c[n][2], -order.index(n)))
        if best not in MARGIN_ONLY:
            continue
        ref = max(settled, key=lambda n: settled[n])
        ratio = c[best][2] / settled[ref] if settled[ref] > 0 else float("inf")
        if pick == best:
            hi = min(hi, ratio)      # marginaalin ALITETTAVA tama jotta best pysyy
            print(f"  {name:14s} pitaa {best} -> marginaali < {ratio:.3f}")
        else:
            lo = max(lo, ratio)      # marginaalin YLITETTAVA tama jotta pudotetaan
            print(f"  {name:14s} pudottaa {best} -> marginaali > {ratio:.3f}")
    print(f"  => {lo:.3f} < marginaali < {hi:.3f}" if lo < hi else
          f"  => EI RATKAISUA ({lo:.3f} !< {hi:.3f})")


if __name__ == "__main__":
    main(*sys.argv[1:])

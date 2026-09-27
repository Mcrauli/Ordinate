"""Koneluettava ajokirjanpito — mitä skanni oli, mitä valittiin, mitä tuli.

`diagnostics.py` kirjoittaa ihmiselle luettavan raportin ongelmatilanteita
varten. Tämä kirjoittaa saman ajon KONEELLE: yksi JSON-rivi per ajo, jotta
kertyneestä joukosta voi myöhemmin päätellä mitkä asetukset toimivat
millaisilla skanneilla. Ilman kirjanpitoa se tieto katoaa jokaisen ajon
mukana, eikä putki voi koskaan oppia mitään omista ajoistaan.

Mitä tästä EI löydy: koordinaatteja, tiedostopolkuja, tiedostonimiä. Skannin
sijainti on asiakkaan tietoa ja tuote lupaa ettei aineisto liiku minnekään —
kirjanpito ei saa olla se paikka jossa lupaus vuotaa. Rakennuksen MITAT
kirjataan, sen PAIKKA ei.

Käyttö on tarkoituksella yksisuuntaista: tämä vain tallentaa. Mikään putken
päätös ei lue tätä tiedostoa, joten vioittunut tai puuttuva loki ei voi
muuttaa ajon tulosta.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_MAX_BYTES = 2_000_000     # ~10 000 ajoa; sitten vanhin puolikas karsitaan


def runs_path() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home()) / "Ordinate"
    return base / "runs.jsonl"


class RunLog:
    """Kerää yhden ajon tiedot ja kirjoittaa ne yhtenä rivinä."""

    def __init__(self, version: str) -> None:
        self.t0 = time.time()
        self.data: dict = {"version": version, "ts": int(self.t0)}

    def scan(self, **kw) -> None:
        """Skannin mitatut piirteet (pisteväli, ala, korkeus, ...)."""
        self.data.setdefault("scan", {}).update(kw)

    def choice(self, what: str, chosen: str, scores: dict | None = None) -> None:
        """Putken tekemä valinta ja se mihin se perustui."""
        entry: dict = {"chosen": chosen}
        if scores:
            entry["scores"] = {k: round(float(v), 4) for k, v in scores.items()}
        self.data.setdefault("choices", {})[what] = entry

    def result(self, **kw) -> None:
        self.data.setdefault("result", {}).update(kw)

    def write(self, path: Path | None = None) -> None:
        """Liitä rivi lokiin. Kirjanpito ei saa koskaan kaataa ajoa."""
        self.data["secs"] = round(time.time() - self.t0, 1)
        target = path or runs_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(self.data, ensure_ascii=False) + "\n")
            self._trim(target)
        except OSError:
            pass

    @staticmethod
    def _trim(target: Path) -> None:
        try:
            if target.stat().st_size <= _MAX_BYTES:
                return
            lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
            target.write_text("".join(lines[len(lines) // 2:]), encoding="utf-8")
        except OSError:
            pass


def load_runs(path: Path | None = None) -> list[dict]:
    """Lue kertynyt kirjanpito. Rikkinäinen rivi ohitetaan, ei kaadeta."""
    target = path or runs_path()
    out: list[dict] = []
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out

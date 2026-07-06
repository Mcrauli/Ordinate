"""Jaettava diagnostiikkaraportti — EI geometriaa, EI koordinaatteja.

Pilottiasiakas ei voi jakaa skanneja (salassapito) → ongelmatilanteessa
riittää tämän tiedoston lähetys: versio, ympäristö, syötetilastot,
vaihelokit aikaleimoineen ja elementtimäärät. Kirjoitetaan aina ajon
loppuun (myös virhetilanteessa) output-hakemistoon."""
from __future__ import annotations

import platform
import time
from pathlib import Path


class DiagnosticsLog:
    def __init__(self) -> None:
        self.t0 = time.time()
        self.lines: list[str] = []
        self.inputs: list[dict] = []
        self.error: str | None = None

    def log(self, msg: str) -> None:
        self.lines.append(f"[{time.time() - self.t0:8.1f}s] {msg}")

    def add_input(self, path: Path) -> None:
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        self.inputs.append({"ext": path.suffix.lower(), "bytes": size})

    def write(self, out_path: Path) -> None:
        from scan2bim._version import __version__
        hdr = [
            "scan2bim-diagnostiikka (ei sisällä geometriaa — turvallinen jakaa)",
            f"versio: {__version__}",
            f"aika: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"kesto: {time.time() - self.t0:.0f} s",
            f"kone: {platform.platform()} / python {platform.python_version()}",
            f"syötteet: {len(self.inputs)} kpl "
            + ", ".join(f"{i['ext']} {i['bytes'] / 1e6:.0f}MB" for i in self.inputs[:20]),
        ]
        if self.error:
            hdr.append(f"VIRHE: {self.error}")
        hdr.append("-" * 60)
        try:
            out_path.write_text("\n".join(hdr + self.lines) + "\n", encoding="utf-8")
        except OSError:
            pass

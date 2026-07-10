"""Jaettava diagnostiikkaraportti — EI geometriaa, EI koordinaatteja.

Pilottiasiakas ei voi jakaa skanneja (salassapito) → ongelmatilanteessa
riittää tämän tiedoston lähetys: versio, ympäristö, syötetilastot,
vaihelokit aikaleimoineen ja elementtimäärät. Kirjoitetaan aina ajon
loppuun (myös virhetilanteessa) output-hakemistoon."""
from __future__ import annotations

import os
import platform
import time
from pathlib import Path

_HISTORY_MAX_BYTES = 3_000_000   # ~viimeiset tuhannet ajot; sitten vanhin karsitaan


def history_path() -> Path:
    """Keskitetty rullaava diagnostiikkaloki (kaikki ajot) — palautesilmukka."""
    base = Path(os.environ.get("APPDATA") or Path.home()) / "scan2bim"
    return base / "diagnostics_history.txt"


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

    def render(self) -> str:
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
        return "\n".join(hdr + self.lines) + "\n"

    def write(self, out_path: Path) -> None:
        text = self.render()
        try:
            out_path.write_text(text, encoding="utf-8")
        except OSError:
            pass
        self._append_history(text)

    def _append_history(self, text: str) -> None:
        """Liitä ajo keskitettyyn rullaavaan lokiin (palautesilmukka)."""
        try:
            hist = history_path()
            hist.parent.mkdir(parents=True, exist_ok=True)
            with open(hist, "a", encoding="utf-8") as f:
                f.write("\n" + "=" * 60 + "\n" + text)
            # Karsi vanhin jos loki kasvaa liian isoksi (säilytä loppu = uusimmat)
            if hist.stat().st_size > _HISTORY_MAX_BYTES:
                data = hist.read_bytes()[-_HISTORY_MAX_BYTES:]
                hist.write_bytes(b"[...vanhempi historia karsittu...]\n" + data)
        except OSError:
            pass

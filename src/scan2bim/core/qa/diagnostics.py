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

_MEM_WORDS = ("bad allocation", "memoryerror", "out of memory", "cannot allocate",
              "unable to allocate", "std::bad_alloc")


def _is_memory_error(msg: str) -> bool:
    low = msg.lower()
    return any(w in low for w in _MEM_WORDS)


def _rss_gb():
    """Prosessin muistinkaytto gigatavuina, None jos ei saatavilla."""
    try:
        import psutil  # noqa: PLC0415
        return psutil.Process().memory_info().rss / 1e9
    except Exception:  # noqa: BLE001 - diagnostiikka ei saa kaataa ajoa
        return None


def _total_ram_gb() -> str:
    try:
        import psutil  # noqa: PLC0415
        vm = psutil.virtual_memory()
        return f"{vm.total / 1e9:.0f} GB (vapaana {vm.available / 1e9:.0f} GB)"
    except Exception:  # noqa: BLE001
        return "?"


def history_path() -> Path:
    """Keskitetty rullaava diagnostiikkaloki (kaikki ajot) — palautesilmukka."""
    base = Path(os.environ.get("APPDATA") or Path.home()) / "scan2bim"
    return base / "diagnostics_history.txt"


class DiagnosticsLog:
    def __init__(self) -> None:
        self.t0 = time.time()
        self._last = self.t0
        self.lines: list[str] = []
        self.inputs: list[dict] = []
        self.error: str | None = None
        self.traceback: str | None = None
        self.peak_gb = 0.0
        self.peak_at = ""
        self.counts: dict[str, int] = {}

    def count(self, **kw: int) -> None:
        """Mita ajo tuotti - elementtimaarat ja pistemaarat."""
        self.counts.update(kw)

    def log(self, msg: str) -> None:
        """Vaiherivi: aikaleima, vaiheen kesto ja muisti.

        Pelkka aikaleima kertoo MILLOIN vaihe alkoi muttei mita se maksoi. Kun
        ajo kaatuu `bad allocation`-virheeseen, ratkaisevat tiedot ovat
        paljonko muistia oli kaytossa ja mika vaihe sen soi. Mitattu koulun
        kellarilla (36 asemaa): loki kertoi vain vaiheen nimen, joten
        juurisyyn selvittaminen vaati koodin lukemista.
        """
        now = time.time()
        dt = now - self._last
        self._last = now
        rss = _rss_gb()
        mem = f" {rss:5.1f}GB" if rss is not None else ""
        self.lines.append(f"[{now - self.t0:8.1f}s +{dt:5.1f}s{mem}] {msg}")
        if rss is not None and rss > self.peak_gb:
            self.peak_gb = rss
            self.peak_at = msg[:60]

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
            f"suoritin: {os.cpu_count()} ydinta   muisti: {_total_ram_gb()}",
            f"syötteet: {len(self.inputs)} kpl, yhteensä "
            f"{sum(i['bytes'] for i in self.inputs) / 1e6:.0f} MB "
            + ", ".join(f"{i['ext']} {i['bytes'] / 1e6:.0f}MB" for i in self.inputs[:20]),
        ]
        if self.peak_gb:
            hdr.append(f"muistihuippu: {self.peak_gb:.1f} GB vaiheessa {self.peak_at!r}")
        if self.counts:
            hdr.append("tulos: " + ", ".join(f"{k}={v:,}" for k, v in self.counts.items()))
        if self.error:
            hdr.append(f"VIRHE: {self.error}")
            if _is_memory_error(self.error):
                hdr.append(
                    "  -> MUISTI LOPPUI. Kokeile: vahemman skanneja kerralla, "
                    "ICP-hienorekisterointi pois, tai suurempi voxel-koko.")
        hdr.append("-" * 60)
        body = list(self.lines)
        if self.traceback:
            body += ["-" * 60, "jalki (kehittajalle):", self.traceback.rstrip()]
        return "\n".join(hdr + body) + "\n"

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

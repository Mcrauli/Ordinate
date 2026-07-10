"""Palautesilmukka: niputa diagnostiikkahistoria + avaa sähköpostiluonnos.

Pilottiasiakas ei voi jakaa skanneja, mutta diagnostiikka (ei geometriaa) +
lyhyt palaute riittää etätukeen ja pilari/palkkimallin parantamiseen. Nappi
tallentaa nipun tiedostoon ja avaa esitäytetyn mailto-viestin — asiakas liittää
tiedoston ja lähettää. Ei backendiä, toimii yrityksen rajoitetussa verkossa."""
from __future__ import annotations

import time
import urllib.parse
import webbrowser
from pathlib import Path

from scan2bim.core.qa.diagnostics import history_path

_DEV_EMAIL = "rekolalauri@gmail.com"

_TEMPLATE = (
    "PALAUTE (täytä lyhyesti):\n"
    "- Ajettuja skanneja / kohteita:\n"
    "- Mikä toimi hyvin:\n"
    "- Mikä meni pieleen / mitä pitäisi korjata:\n"
    "- Väärät detektiot (mitkä palkit/pilarit/seinät olivat väärin):\n"
    "\n" + "=" * 60 + "\nDIAGNOSTIIKKAHISTORIA (ei geometriaa, turvallinen jakaa):\n\n"
)


def _desktop() -> Path:
    d = Path.home() / "Desktop"
    return d if d.exists() else Path.home()


def export_and_mail() -> tuple[Path | None, str]:
    """Tallenna diagnostiikkanippu ja avaa mailto. Palauttaa (polku, viesti)."""
    hist = history_path()
    if not hist.exists() or hist.stat().st_size == 0:
        return None, ("Ei vielä diagnostiikkaa lähetettäväksi.\n"
                      "Aja ensin ainakin yksi konvertointi.")
    try:
        body_hist = hist.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return None, f"Diagnostiikan luku epäonnistui: {e}"

    dest = _desktop() / f"scan2bim-diagnostiikka-{time.strftime('%Y%m%d_%H%M')}.txt"
    try:
        dest.write_text(_TEMPLATE + body_hist, encoding="utf-8")
    except OSError as e:
        return None, f"Tallennus epäonnistui: {e}"

    from scan2bim._version import __version__
    subject = f"scan2bim diagnostiikka & palaute (v{__version__})"
    body = (
        f"Diagnostiikka tallennettu tiedostoon:\n{dest}\n\n"
        "Liitä yllä oleva tiedosto tähän viestiin (raahaa se liitteeksi).\n\n"
        "Palaute:\n- Mikä toimi:\n- Mikä meni pieleen:\n"
        "- Väärät detektiot (palkit/pilarit):\n"
    )
    url = "mailto:" + _DEV_EMAIL + "?" + urllib.parse.urlencode(
        {"subject": subject, "body": body}, quote_via=urllib.parse.quote
    )
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 — mailto voi puuttua; tiedosto on silti tallessa
        pass
    return dest, (f"Diagnostiikka tallennettu:\n{dest}\n\n"
                  "Sähköpostiluonnos avautui — LIITÄ tiedosto ja lähetä.\n"
                  "Jos sähköposti ei auennut, lähetä tiedosto käsin osoitteeseen "
                  f"{_DEV_EMAIL}.")

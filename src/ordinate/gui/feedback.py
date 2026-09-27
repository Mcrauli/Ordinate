"""Palautesilmukka: niputa diagnostiikkahistoria + avaa sähköpostiluonnos.

Pilottiasiakas ei voi jakaa skanneja, mutta diagnostiikka (ei geometriaa) +
lyhyt palaute riittää etätukeen ja pilari/palkkimallin parantamiseen. Nappi
tallentaa nipun tiedostoon ja tarjoaa esitäytetyn viestin — asiakas liittää
tiedoston ja lähettää. Ei backendiä, toimii yrityksen rajoitetussa verkossa.

HUOM: mailto voi epäonnistua HILJAA (Windowsin mailto-kytkös voi osoittaa
poistettuun sovellukseen, os.startfile ei heitä virhettä) — siksi dialogi
näyttää aina osoitteen + aiheen ja tarjoaa myös Gmail-selainlinkin."""
from __future__ import annotations

import os
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

from ordinate.core.qa.diagnostics import history_path

DEV_EMAIL = "rekolalauri@gmail.com"

_TEMPLATE = (
    "PALAUTE (täytä lyhyesti):\n"
    "- Ajettuja skanneja / kohteita:\n"
    "- Mikä toimi hyvin:\n"
    "- Mikä meni pieleen / mitä pitäisi korjata:\n"
    "- Väärät detektiot (mitkä palkit/pilarit/seinät olivat väärin):\n"
    "\n" + "=" * 60 + "\nDIAGNOSTIIKKAHISTORIA (ei geometriaa, turvallinen jakaa):\n\n"
)

_MAIL_BODY = (
    "Liitä työpöydälle tallennettu diagnostiikkatiedosto tähän viestiin.\n\n"
    "Palaute:\n- Mikä toimi:\n- Mikä meni pieleen:\n"
    "- Väärät detektiot (palkit/pilarit):\n"
)


def _desktop() -> Path:
    d = Path.home() / "Desktop"
    return d if d.exists() else Path.home()


def mail_subject() -> str:
    from ordinate._version import __version__
    return f"Ordinate diagnostiikka & palaute (v{__version__})"


def export_bundle() -> tuple[Path | None, str]:
    """Tallenna diagnostiikkanippu työpöydälle. Palauttaa (polku, virheviesti)."""
    hist = history_path()
    if not hist.exists() or hist.stat().st_size == 0:
        return None, ("Ei vielä diagnostiikkaa lähetettäväksi.\n"
                      "Aja ensin ainakin yksi konvertointi.")
    try:
        body_hist = hist.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return None, f"Diagnostiikan luku epäonnistui: {e}"

    dest = _desktop() / f"Ordinate-diagnostiikka-{time.strftime('%Y%m%d_%H%M')}.txt"
    try:
        dest.write_text(_TEMPLATE + body_hist, encoding="utf-8")
    except OSError as e:
        return None, f"Tallennus epäonnistui: {e}"
    return dest, ""


def open_mail_client() -> None:
    """Avaa oletussähköpostiohjelman luonnos (vastaanottaja + aihe + runko)."""
    url = "mailto:" + DEV_EMAIL + "?" + urllib.parse.urlencode(
        {"subject": mail_subject(), "body": _MAIL_BODY},
        quote_via=urllib.parse.quote,
    )
    try:
        if sys.platform == "win32":
            os.startfile(url)  # noqa: S606 — mailto oletussovellukseen
        else:
            webbrowser.open(url)
    except OSError:
        pass  # dialogissa näkyy osoite + aihe käsin lähetystä varten


def open_gmail() -> None:
    """Avaa Gmailin luonnos selaimessa (toimii vaikka mailto-kytkös on rikki)."""
    url = "https://mail.google.com/mail/?" + urllib.parse.urlencode(
        {"view": "cm", "fs": "1", "to": DEV_EMAIL,
         "su": mail_subject(), "body": _MAIL_BODY},
        quote_via=urllib.parse.quote,
    )
    webbrowser.open(url)

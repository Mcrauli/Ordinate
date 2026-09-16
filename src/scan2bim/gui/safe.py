r"""Slotin virhe näkyviin, ei prosessin tappoon.

PySide6 kutsuu `abort()`ia kun Python-poikkeus jää käsittelemättä slotissa:
ikkuna vain katoaa, eikä käyttäjä saa mitään. Näin kävi kahdesti 16.9.2026
(0xc0000409, pääsäie Qt:n tapahtumasilmukassa) ilman riviäkään lokia.

`@guard` kirjaa poikkeuksen lokiin, kertoo käyttäjälle kerran ja antaa
sovelluksen jatkaa. Se EI piilota vikaa — loki on `%TEMP%\scan2bim_gui.log`
ja virheilmoitus kertoo mistä toiminnosta on kyse.
"""
from __future__ import annotations

import datetime
import functools
import sys
import traceback

NL = chr(10)
LOG = "%TEMP%" + chr(92) + "scan2bim_gui.log"
_seen: set[str] = set()


def guard(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            _report(fn.__name__, exc, self)
            return None
    return wrapper


def _report(where: str, exc: Exception, owner=None) -> None:
    try:
        print(f"\n=== VIRHE {datetime.datetime.now():%Y-%m-%d %H:%M:%S} {where} ===",
              file=sys.stderr)
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass
    key = f"{where}:{type(exc).__name__}"
    if key in _seen:
        return
    _seen.add(key)
    try:
        from PySide6 import QtCore, QtWidgets
        if QtWidgets.QApplication.instance() is None:
            return
        parent = owner if isinstance(owner, QtWidgets.QWidget) else None
        # EI-MODAALI: modaali dialogi jaa odottamaan klikkausta ja jaadyttaa
        # sovelluksen — virheilmoitus ei saa olla uusi jaatyma.
        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Icon.Warning, "Virhe",
            f"Toiminto {where!r} epaonnistui:{NL}{type(exc).__name__}: {exc}{NL}{NL}"
            f"Sovellus jatkaa. Virhe on kirjattu lokiin:{NL}{LOG}",
            QtWidgets.QMessageBox.StandardButton.Ok, parent)
        box.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)
        box.show()
    except Exception:  # noqa: BLE001
        pass

"""GUI-käynnistys."""
from __future__ import annotations

import sys

from PySide6 import QtWidgets

from scan2bim.gui.main_window import MainWindow
from scan2bim.gui.theme import apply_theme
from scan2bim.gui.brand import app_icon

# Nimetty mutex jonka asennusohjelma (installer.iss: AppMutex) tunnistaa → osaa
# pyytää sulkemaan käynnissä olevan sovelluksen ENNEN kuin se yrittää korvata
# scan2bim.exe:n (muuten Windows-virhe 32: "tiedosto toisen prosessin käytössä").
# Kahvaa ei suljeta → mutex elää prosessin eliniän. No-op muualla kuin Windowsissa.
_APP_MUTEX_NAME = "Scan2BimAppMutex"
_mutex_handle = None


def _acquire_app_mutex() -> None:
    global _mutex_handle
    if sys.platform != "win32" or _mutex_handle is not None:
        return
    try:
        import ctypes
        _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, _APP_MUTEX_NAME)
    except Exception:
        _mutex_handle = None  # mutex on vain asennus-avustus, ei saa kaataa appia


def _install_crash_log() -> None:
    """Kirjaa käsittelemätön poikkeus lokiin ENNEN kuin PySide6 tappaa prosessin.

    PySide6 kutsuu `abort()`ia kun poikkeus jää käsittelemättä slotissa, joten
    ilman tätä käyttäjä näkee vain ikkunan katoavan.
    """
    import datetime
    import threading
    import traceback

    def _log(exc_type, exc, tb, where: str = "") -> None:
        try:
            print(f"\n=== KAATUI {datetime.datetime.now():%Y-%m-%d %H:%M:%S} {where} ===",
                  file=sys.stderr)
            traceback.print_exception(exc_type, exc, tb, file=sys.stderr)
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = _log
    threading.excepthook = lambda a: _log(a.exc_type, a.exc_value, a.exc_traceback,
                                          f"säikeessä {a.thread.name if a.thread else '?'}")


def run() -> None:
    _install_crash_log()
    _acquire_app_mutex()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

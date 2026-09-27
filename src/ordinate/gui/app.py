"""GUI-käynnistys."""
from __future__ import annotations

import sys

from PySide6 import QtWidgets

from ordinate.gui.main_window import MainWindow
from ordinate.gui.theme import apply_theme
from ordinate.gui.brand import app_icon

# Nimetty mutex jonka asennusohjelma (installer.iss: AppMutex) tunnistaa → osaa
# pyytää sulkemaan käynnissä olevan sovelluksen ENNEN kuin se yrittää korvata
# ordinate.exe:n (muuten Windows-virhe 32: "tiedosto toisen prosessin käytössä").
# Kahvaa ei suljeta → mutex elää prosessin eliniän. No-op muualla kuin Windowsissa.
_APP_MUTEX_NAME = "OrdinateAppMutex"
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


def _clean_stale_temp(max_age_h: float = 12.0) -> None:
    """3D-tarkastuksen välitiedostot (~100 MB kpl) jäävät jos istunto kaatuu.

    Vain vanhat poistetaan: toinen käynnissä oleva ikkuna voi käyttää tuoreita.
    """
    import tempfile
    import time
    from pathlib import Path

    cutoff = time.time() - max_age_h * 3600.0
    for pat in ("s2b_view_*.npz", "s2b_model_*.json"):
        for f in Path(tempfile.gettempdir()).glob(pat):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass


def run() -> None:
    _install_crash_log()
    _clean_stale_temp()
    _acquire_app_mutex()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

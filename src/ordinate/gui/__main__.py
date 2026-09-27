"""GUI-käynnistys + kaatumisloki.

PyInstaller --windowed (console=False) → sys.stdout/stderr ovat None. Mikä
tahansa print() tai logging (lastResort-handler kirjoittaa sys.stderr:iin)
kaatuisi tällöin: 'NoneType' object has no attribute 'write'.

MUTTA pelkkä sys.stderr:n ohjaus ei riitä: PySide6 tappaa prosessin
`abort()`illa kun Python-poikkeus jää käsittelemättä slotissa, ja se jälki
kirjoitetaan C-tason stderriin (fd 2). Windowed-exessä fd 2 ei osoita
mihinkään, joten kaatumisesta ei jäänyt mitään — sovellus kaatui kahdesti
16.9.2026 eikä lokissa ollut riviäkään. Siksi fd 1 ja 2 ohjataan `os.dup2`:lla
samaan tiedostoon ja `faulthandler` kytketään päälle.
"""
import datetime
import faulthandler
import os
import sys
import tempfile

LOG_PATH = os.path.join(tempfile.gettempdir(), "ordinate_gui.log")
_windowed = sys.stdout is None or sys.stderr is None

try:
    _logf = open(LOG_PATH, "a", encoding="utf-8", errors="replace", buffering=1)
except OSError:
    _logf = open(os.devnull, "w")

if _windowed:
    # Vain ikkunatilassa: kehityksessä konsoli saa pysyä konsolina.
    for _fd in (1, 2):
        try:
            os.dup2(_logf.fileno(), _fd)
        except (OSError, ValueError, AttributeError):
            pass
    if sys.stdout is None:
        sys.stdout = _logf
    if sys.stderr is None:
        sys.stderr = _logf

try:
    faulthandler.enable(_logf)
except (OSError, ValueError, AttributeError):
    pass

try:
    from ordinate._version import __version__ as _v
except Exception:  # noqa: BLE001
    _v = "?"
print(f"\n=== Ordinate {_v} käynnistyi {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===",
      file=_logf, flush=True)

from ordinate.gui.app import run  # noqa: E402

run()

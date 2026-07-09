import os
import sys
import tempfile

# PyInstaller --windowed (console=False) → sys.stdout/stderr ovat None. Mikä
# tahansa print() tai logging (lastResort-handler kirjoittaa sys.stderr:iin)
# kaatuisi tällöin: 'NoneType' object has no attribute 'write' (esim. katkenneen
# PLY:n log.warning). Ohjataan None-virrat lokitiedostoon ENNEN muita importteja.
if sys.stdout is None or sys.stderr is None:
    try:
        _logf = open(
            os.path.join(tempfile.gettempdir(), "scan2bim_gui.log"),
            "a", encoding="utf-8", errors="replace",
        )
    except OSError:
        _logf = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = _logf
    if sys.stderr is None:
        sys.stderr = _logf

from scan2bim.gui.app import run

run()

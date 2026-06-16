"""GUI-käynnistys."""
from __future__ import annotations

import sys

from PySide6 import QtWidgets

from scan2bim.gui.main_window import MainWindow
from scan2bim.gui.theme import apply_theme
from scan2bim.gui.brand import app_icon


def run() -> None:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()

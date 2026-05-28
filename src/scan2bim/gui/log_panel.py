"""Loki- ja tulospaneeli (oikea puoli)."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim.gui.theme import ACCENT, ERROR, SUCCESS, TEXT_DIM, WARN


class LogPanel(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QtWidgets.QLabel("Loki")
        header.setObjectName("section")
        layout.addWidget(header)

        self._log = QtWidgets.QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(300)
        layout.addWidget(self._log, stretch=1)

        self._results = QtWidgets.QLabel("")
        self._results.setWordWrap(True)
        self._results.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
        layout.addWidget(self._results)

    def append(self, msg: str, color: str | None = None) -> None:
        c = color or "#f1f5f9"
        self._log.append(f'<span style="color:{c};">{msg}</span>')
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )

    def info(self, msg: str) -> None:
        self.append(msg)

    def success(self, msg: str) -> None:
        self.append(msg, SUCCESS)

    def error(self, msg: str) -> None:
        self.append(msg, ERROR)

    def warn(self, msg: str) -> None:
        self.append(msg, WARN)

    def set_results(self, summary: str) -> None:
        self._results.setText(summary)

    def clear(self) -> None:
        self._log.clear()
        self._results.clear()

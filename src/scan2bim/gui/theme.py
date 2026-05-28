"""Sovelluksen visuaalinen teema."""
from __future__ import annotations

from PySide6 import QtGui, QtWidgets

ACCENT = "#2563eb"       # sininen
ACCENT_HOVER = "#1d4ed8"
BG = "#0f172a"
BG_PANEL = "#1e293b"
BG_WIDGET = "#334155"
TEXT = "#f1f5f9"
TEXT_DIM = "#94a3b8"
SUCCESS = "#22c55e"
ERROR = "#ef4444"
WARN = "#f59e0b"

QSS = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}}
QSplitter::handle {{ background: {BG_WIDGET}; width: 1px; height: 1px; }}

/* Paneelit */
QFrame#panel {{
    background: {BG_PANEL};
    border-radius: 8px;
}}

/* Painikkeet */
QPushButton {{
    background: {ACCENT};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:disabled {{ background: {BG_WIDGET}; color: {TEXT_DIM}; }}

/* Kentät */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {BG_WIDGET};
    border: 1px solid #475569;
    border-radius: 5px;
    padding: 5px 8px;
    color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}

/* Lokilaatikko */
QTextEdit {{
    background: #020617;
    border: 1px solid #1e293b;
    border-radius: 6px;
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
    color: {TEXT};
}}

/* Otsikot */
QLabel#title {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#subtitle {{
    font-size: 12px;
    color: {TEXT_DIM};
}}
QLabel#section {{
    font-size: 11px;
    font-weight: 600;
    color: {TEXT_DIM};
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* Statusbar */
QStatusBar {{ background: {BG_PANEL}; color: {TEXT_DIM}; font-size: 12px; }}

/* Progressbar */
QProgressBar {{
    background: {BG_WIDGET};
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

/* Scrollbar */
QScrollBar:vertical {{
    background: {BG_PANEL}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BG_WIDGET}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


def apply_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(BG))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(TEXT))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(BG_PANEL))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(TEXT))
    app.setPalette(palette)

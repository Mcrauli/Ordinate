"""Sovelluksen visuaalinen teema."""
from __future__ import annotations

from PySide6 import QtGui, QtWidgets

ACCENT = "#c6f24e"       # keilaus-lime (brändiväri)
ACCENT_HOVER = "#b3e635"
ACCENT_2 = "#39d0d8"     # point-cloud cyan
BG = "#0a0e14"
BG_PANEL = "#121a26"
BG_WIDGET = "#1e2a3a"
TEXT = "#e6edf5"
TEXT_DIM = "#8194a8"
SUCCESS = "#22c55e"
ERROR = "#ef4444"
WARN = "#ffb454"

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
    color: #0a0e14;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 700;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:disabled {{ background: {BG_WIDGET}; color: {TEXT_DIM}; }}

/* Toissijainen "link"-painike (avaa kansio, palaute) — huomaamaton */
QPushButton#linkbtn {{
    background: transparent;
    color: {TEXT_DIM};
    font-weight: 600;
    padding: 8px 12px;
}}
QPushButton#linkbtn:hover {{ background: {BG_WIDGET}; color: {ACCENT}; }}

/* Välilehdet */
QTabWidget::pane {{ border: 1px solid {BG_WIDGET}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background: {BG_PANEL};
    color: {TEXT_DIM};
    padding: 8px 18px;
    border: 1px solid {BG_WIDGET};
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    font-weight: 600;
}}
QTabBar::tab:selected {{ background: {BG_WIDGET}; color: {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

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

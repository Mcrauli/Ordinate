"""Sovelluksen visuaalinen teema — tumma, viimeistelty, lime-brändiaksentti."""
from __future__ import annotations

from PySide6 import QtGui, QtWidgets

ACCENT = "#c6f24e"       # keilaus-lime (brändiväri)
ACCENT_HOVER = "#d4f96a"
ACCENT_PRESS = "#b3e635"
ACCENT_2 = "#39d0d8"     # point-cloud cyan
BG = "#0a0d13"           # sisältötausta (lähes musta, sinertävä)
BG_PANEL = "#121924"     # sivupalkki / kortit
BG_WIDGET = "#1b2531"    # syöttökentät / chipit
BG_HOVER = "#222e3d"
BORDER = "#212c3a"       # hienovarainen reuna
BORDER_STRONG = "#2d3b4d"
TEXT = "#e8eef6"
TEXT_DIM = "#93a3b8"
TEXT_MUTED = "#61728a"
SUCCESS = "#4ade80"
ERROR = "#f87171"
WARN = "#fbbf24"

QSS = f"""
* {{ outline: 0; }}
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

/* Sivupalkki */
QWidget#sidebar {{
    background: {BG_PANEL};
    border-right: 1px solid {BORDER};
}}
QScrollArea#sidebarscroll {{ background: transparent; border: none; }}
QWidget#sidebarcontent {{ background: transparent; }}
QWidget#sidebarfooter {{ background: {BG_PANEL}; border-top: 1px solid {BORDER}; }}

/* Kortit / palkit */
QFrame#panel {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QSplitter::handle {{ background: {BORDER}; width: 1px; }}

/* Ensisijainen painike (lime) */
QPushButton {{
    background: {ACCENT};
    color: #0a0d13;
    border: none;
    border-radius: 7px;
    padding: 9px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {ACCENT_PRESS}; }}
QPushButton:disabled {{ background: {BG_WIDGET}; color: {TEXT_MUTED}; }}

/* Toissijainen "ghost"-painike */
QPushButton#ghost, QPushButton#linkbtn {{
    background: transparent;
    color: {TEXT_DIM};
    border: 1px solid {BORDER_STRONG};
    font-weight: 600;
    padding: 8px 14px;
}}
QPushButton#ghost:hover, QPushButton#linkbtn:hover {{
    background: {BG_HOVER}; color: {TEXT}; border-color: {TEXT_MUTED};
}}
/* Pieni ikoni-/selauspainike */
QPushButton#iconbtn {{
    background: {BG_WIDGET}; color: {TEXT_DIM};
    border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    padding: 0; font-weight: 700; font-size: 15px;
}}
QPushButton#iconbtn:hover {{ background: {BG_HOVER}; color: {TEXT}; }}

/* Välilehdet */
QTabWidget::pane {{ border: none; top: 0; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 9px 16px;
    margin-right: 4px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

/* Kentät */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {BG_WIDGET};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 7px 10px;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #0a0d13;
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:hover, QComboBox:hover {{ border-color: {TEXT_MUTED}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM}; margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {BG_WIDGET}; border: 1px solid {BORDER_STRONG};
    border-radius: 8px; padding: 4px;
    selection-background-color: {BG_HOVER}; selection-color: {TEXT};
    outline: 0;
}}

/* Valintaruudut — täytetty lime-laatikko = päällä */
QCheckBox {{ spacing: 9px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 17px; height: 17px; border-radius: 5px;
    border: 1.5px solid {BORDER_STRONG}; background: transparent;
}}
QCheckBox::indicator:hover {{ border-color: {TEXT_MUTED}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
    image: url({{_CHECK_URL}});
}}
QCheckBox:disabled {{ color: {TEXT_MUTED}; }}

/* Lokilaatikko */
QTextEdit {{
    background: #060a10;
    border: 1px solid {BORDER};
    border-radius: 8px;
    font-family: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
    color: {TEXT_DIM};
    padding: 6px;
}}

/* Otsikot */
QLabel#title {{ font-size: 19px; font-weight: 700; color: {TEXT}; }}
QLabel#subtitle {{ font-size: 12px; color: {TEXT_DIM}; }}
QLabel#section {{
    font-size: 11px; font-weight: 700; color: {TEXT_MUTED};
    text-transform: uppercase; letter-spacing: 1.2px;
}}

/* Statusbar */
QStatusBar {{
    background: {BG_PANEL}; color: {TEXT_MUTED};
    font-size: 12px; border-top: 1px solid {BORDER};
}}
QStatusBar::item {{ border: none; }}

/* Progressbar */
QProgressBar {{ background: {BG_WIDGET}; border-radius: 3px; height: 5px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}

/* Scrollbar */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 4px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; border-radius: 4px; min-width: 24px; }}
QScrollBar::handle:horizontal:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* Tooltip */
QToolTip {{
    background: {BG_WIDGET}; color: {TEXT};
    border: 1px solid {BORDER_STRONG}; border-radius: 6px; padding: 6px 8px;
}}

/* Listat */
QListWidget {{
    background: {BG_WIDGET}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 4px; outline: 0;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {BG_HOVER}; }}
QListWidget::item:selected {{ background: {BG_HOVER}; color: {ACCENT}; }}
"""


def _checkmark_path() -> str:
    """Piirrä lime-checkmark valintaruudun sisään (valkoinen veto lime-pohjalle).
    Palauttaa QSS-yhteensopivan url-polun (PNG scratch-tiedostoon)."""
    import tempfile
    from PySide6 import QtCore
    size = 17
    img = QtGui.QImage(size, size, QtGui.QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor("#0a0d13"), 2.2)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline(QtGui.QPolygonF([
        QtCore.QPointF(4.0, 8.8), QtCore.QPointF(7.2, 12.0), QtCore.QPointF(13.0, 5.2)]))
    p.end()
    f = tempfile.NamedTemporaryFile(suffix="_check.png", delete=False)
    img.save(f.name, "PNG")
    return f.name.replace("\\", "/")


_CHECK_URL = ""


def apply_theme(app: QtWidgets.QApplication) -> None:
    global _CHECK_URL, QSS
    app.setStyle("Fusion")
    if not _CHECK_URL:
        try:
            _CHECK_URL = _checkmark_path()
            QSS = QSS.replace("{_CHECK_URL}", _CHECK_URL)
        except Exception:
            QSS = QSS.replace("image: url({_CHECK_URL});", "")
    app.setStyleSheet(QSS)
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(BG))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(TEXT))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(BG_WIDGET))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(TEXT))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(BG_WIDGET))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(TEXT))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(ACCENT))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(BG))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(BG_WIDGET))
    palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(TEXT))
    app.setPalette(palette)

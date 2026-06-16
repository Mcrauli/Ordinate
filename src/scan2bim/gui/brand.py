"""Canonical scan2bim brand mark, drawn with QPainter.

Same design as assets/scan2bim.svg and the site logo: dark rounded "scan
bay" square, lime border, cyan registration crosshair, lime centre dot.
Rendered live so the GUI needs no bundled image and stays pixel-consistent
with the icon/site.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui

_BG = QtGui.QColor("#0a0e14")
_LIME = QtGui.QColor("#c6f24e")
_CYAN = QtGui.QColor("#39d0d8")


def logo_pixmap(size: int = 64) -> QtGui.QPixmap:
    px = QtGui.QPixmap(size, size)
    px.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(px)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    m = size / 256.0

    p.setPen(QtGui.QPen(_LIME, 12 * m))
    p.setBrush(_BG)
    p.drawRoundedRect(QtCore.QRectF(20 * m, 20 * m, 216 * m, 216 * m), 40 * m, 40 * m)

    pen = QtGui.QPen(_CYAN, 12 * m)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(128 * m, 74 * m), QtCore.QPointF(128 * m, 182 * m))
    p.drawLine(QtCore.QPointF(74 * m, 128 * m), QtCore.QPointF(182 * m, 128 * m))

    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(_LIME)
    p.drawEllipse(QtCore.QPointF(128 * m, 128 * m), 26 * m, 26 * m)
    p.end()
    return px


def app_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    for s in (16, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s))
    return icon

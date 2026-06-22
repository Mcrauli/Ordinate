"""Pohjapiirros-esikatselu: piirtää StructuralModelin (seinät, huoneet, aukot)
interaktiiviseen QGraphicsView'iin. Zoom rullalla, panoroi raahaamalla."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim.gui.theme import ACCENT, ACCENT_2, BG, BG_PANEL, TEXT, TEXT_DIM

_ROOM_FILLS = [
    "#39d0d8", "#c6f24e", "#ff9e64", "#bb9af7",
    "#7dcfff", "#f7768e", "#9ece6a", "#e0af68",
]


class PlanView(QtWidgets.QWidget):
    """Interaktiivinen pohjapiirros usean kerroksen tuella."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._models: list = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        bar = QtWidgets.QHBoxLayout()
        self._floor_combo = QtWidgets.QComboBox()
        self._floor_combo.currentIndexChanged.connect(self._render_current)
        self._floor_combo.setVisible(False)
        bar.addWidget(self._floor_combo)
        bar.addStretch()
        self._stats = QtWidgets.QLabel("")
        self._stats.setObjectName("subtitle")
        bar.addWidget(self._stats)
        layout.addLayout(bar)

        self._scene = QtWidgets.QGraphicsScene(self)
        self._view = QtWidgets.QGraphicsView(self._scene)
        self._view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._view.setBackgroundBrush(QtGui.QColor(BG))
        self._view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self._view.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        layout.addWidget(self._view, stretch=1)

        self._placeholder = QtWidgets.QLabel(
            "Pohjapiirros näkyy tässä konversion jälkeen."
        )
        self._placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color:{TEXT_DIM};font-size:14px;")
        layout.addWidget(self._placeholder)
        self._view.setVisible(False)

    # --- julkinen API ---------------------------------------------------------

    def show_models(self, models: list) -> None:
        self._models = [m for m in models if m is not None]
        self._floor_combo.blockSignals(True)
        self._floor_combo.clear()
        for i, _ in enumerate(self._models):
            self._floor_combo.addItem(f"Kerros {i}")
        self._floor_combo.blockSignals(False)
        self._floor_combo.setVisible(len(self._models) > 1)
        if self._models:
            self._placeholder.setVisible(False)
            self._view.setVisible(True)
            self._floor_combo.setCurrentIndex(0)
            self._render_current()

    def show_model(self, model) -> None:
        self.show_models([model])

    # --- piirto ---------------------------------------------------------------

    def _render_current(self) -> None:
        if not self._models:
            return
        idx = max(0, self._floor_combo.currentIndex())
        model = self._models[min(idx, len(self._models) - 1)]
        self._draw(model)

    def _draw(self, model) -> None:
        self._scene.clear()
        # Y käännetään (maailman y ylös, ruudun y alas).
        flip = QtGui.QTransform().scale(1, -1)

        # Huoneet
        for i, sp in enumerate(getattr(model, "spaces", []) or []):
            poly = QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in sp.boundary])
            fill = QtGui.QColor(_ROOM_FILLS[i % len(_ROOM_FILLS)])
            fill.setAlpha(55)
            item = self._scene.addPolygon(
                flip.map(poly),
                QtGui.QPen(QtGui.QColor(ACCENT_2), 12),
                QtGui.QBrush(fill),
            )
            item.setZValue(0)
            c = flip.map(poly).boundingRect().center()
            area = _polygon_area(sp.boundary) / 1e6  # m²
            label = self._scene.addText(f"{area:.1f} m2")
            label.setDefaultTextColor(QtGui.QColor(TEXT))
            f = label.font(); f.setPointSize(11); f.setBold(True); label.setFont(f)
            label.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            label.setPos(c)
            label.setZValue(3)

        # Seinät
        wall_pen = QtGui.QPen(QtGui.QColor("#cbd5e1"))
        wall_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        for w in getattr(model, "walls", []) or []:
            (x0, y0), (x1, y1) = w.axis[0], w.axis[1]
            wall_pen.setWidthF(max(float(w.thickness), 60.0))
            line = self._scene.addLine(x0, -y0, x1, -y1, wall_pen)
            line.setZValue(1)

        # Aukot (ovet/ikkunat)
        for op in getattr(model, "openings", []) or []:
            w = next((w for w in model.walls if w.id == op.wall_id), None)
            if not w:
                continue
            (x0, y0), (x1, y1) = w.axis[0], w.axis[1]
            import math
            L = math.hypot(x1 - x0, y1 - y0) or 1.0
            t = op.position_along / L
            px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            col = ACCENT if op.opening_type == "door" else ACCENT_2
            dot = self._scene.addEllipse(
                px - 120, -py - 120, 240, 240,
                QtGui.QPen(QtCore.Qt.PenStyle.NoPen), QtGui.QBrush(QtGui.QColor(col)),
            )
            dot.setZValue(2)

        self._view.setSceneRect(self._scene.itemsBoundingRect().adjusted(-500, -500, 500, 500))
        self._view.fitInView(self._scene.itemsBoundingRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

        nw = len(getattr(model, "walls", []) or [])
        ns = len(getattr(model, "spaces", []) or [])
        no = len(getattr(model, "openings", []) or [])
        self._stats.setText(f"{nw} seinää · {ns} huonetta · {no} aukkoa")

    # --- vuorovaikutus --------------------------------------------------------

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._view.scale(factor, factor)


def _polygon_area(pts: list) -> float:
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0

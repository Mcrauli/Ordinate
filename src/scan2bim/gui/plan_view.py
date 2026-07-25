"""Pohjapiirros-esikatselu: piirtää StructuralModelin (seinät, huoneet, ovet,
ikkunat) arkkitehtisymbolein interaktiiviseen QGraphicsView'iin.
Zoom rullalla, panoroi raahaamalla. Taustaruudukko 1 m, mittajana alhaalla."""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim.core.qa.deviation import flag_low_confidence
from scan2bim.gui.theme import ACCENT, ACCENT_2, BG, BG_PANEL, TEXT, TEXT_DIM

_FLAG_COLOR = "#ff5c5c"    # tarkistettava (matala luottamus)

_ROOM_FILLS = [
    "#39d0d8", "#c6f24e", "#ff9e64", "#bb9af7",
    "#7dcfff", "#f7768e", "#9ece6a", "#e0af68",
]
_WALL_COLOR = "#e6edf7"
_GRID_MM = 1000.0          # taustaruudukon väli (1 m)
_DOOR_COLOR = "#ffb35c"
_WINDOW_COLOR = "#7dcfff"
_SLAB_COLOR = "#5b6b7f"     # lattia-footprintin ääriviiva (himmeä)
_BEAM_COLOR = "#bb9af7"     # palkki (katkoviiva, yläpuolinen)
_COLUMN_FILL = "#e0af68"    # pilari (umpitäyttö)
_COLUMN_EDGE = "#8a6a3c"


class _PlanGraphicsView(QtWidgets.QGraphicsView):
    """Vasen klikkaus = valitse elementti, vasen veto tyhjästä = maalaa valinta-
    laatikko (monta), keski/oikea veto = panoroi, rulla = zoom."""

    def __init__(self, scene, parent=None) -> None:
        super().__init__(scene, parent)
        self._pick = None       # callback(kind|None, id|None)
        self._box_pick = None   # callback(list[(kind,id)])
        self._pan = None
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)

    def _data_at(self, pos):
        for it in self.items(pos):
            if it.data(0) is not None:
                return it.data(0)
        return None

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        b = event.button()
        if b == QtCore.Qt.MouseButton.LeftButton and self._pick is not None:
            data = self._data_at(event.position().toPoint())
            if data is not None:
                self._pick(data[0], data[1])
                event.accept()
                return
            self._pick(None, None)   # tyhjä → poista valinta, aloita maalaus
        elif b in (QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.MouseButton.RightButton):
            self._pan = event.position()
            self.viewport().setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._pan is not None:
            d = event.position() - self._pan
            self._pan = event.position()
            hb = self.horizontalScrollBar(); vb = self.verticalScrollBar()
            hb.setValue(hb.value() - int(d.x())); vb.setValue(vb.value() - int(d.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._pan is not None and event.button() in (
                QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.MouseButton.RightButton):
            self._pan = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)   # viimeistelee valintalaatikon
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._box_pick is not None:
            pairs = [it.data(0) for it in self.scene().selectedItems() if it.data(0) is not None]
            self.scene().clearSelection()
            if pairs:
                self._box_pick(pairs)

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        painter.fillRect(rect, QtGui.QColor(BG))
        # Näytä ruudukko vain kun ruudut ovat järkevän kokoisia (ei sumua kaukaa).
        px_per_mm = self.transform().m11()
        if px_per_mm * _GRID_MM < 6:
            return
        left = math.floor(rect.left() / _GRID_MM) * _GRID_MM
        top = math.floor(rect.top() / _GRID_MM) * _GRID_MM
        fine = QtGui.QPen(QtGui.QColor(255, 255, 255, 12))
        fine.setCosmetic(True)
        painter.setPen(fine)
        x = left
        while x < rect.right():
            painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            x += _GRID_MM
        y = top
        while y < rect.bottom():
            painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))
            y += _GRID_MM

    def drawForeground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        # Mittajana kiinteänä viewport-koordinaatistossa (ei zoomaudu).
        painter.save()
        painter.resetTransform()
        px_per_mm = self.transform().m11()
        if px_per_mm <= 0:
            painter.restore(); return
        # Valitse "siisti" metrimäärä jonka jana on ~90–160 px.
        target_px = 120.0
        raw_mm = target_px / px_per_mm
        nice = _nice_length_mm(raw_mm)
        bar_px = nice * px_per_mm
        vh = self.viewport().height()
        x0, y0 = 20.0, vh - 24.0
        pen = QtGui.QPen(QtGui.QColor(TEXT), 2)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(x0, y0), QtCore.QPointF(x0 + bar_px, y0))
        painter.drawLine(QtCore.QPointF(x0, y0 - 5), QtCore.QPointF(x0, y0 + 5))
        painter.drawLine(QtCore.QPointF(x0 + bar_px, y0 - 5), QtCore.QPointF(x0 + bar_px, y0 + 5))
        label = f"{nice/1000:.0f} m" if nice >= 1000 else f"{nice:.0f} mm"
        painter.setPen(QtGui.QColor(TEXT_DIM))
        painter.drawText(QtCore.QPointF(x0, y0 - 8), label)
        painter.restore()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self.viewport().update()


def _nice_length_mm(raw: float) -> float:
    """Lähin 'siisti' pituus (1/2/5 × 10ⁿ) mm."""
    if raw <= 0:
        return 1000.0
    exp = math.floor(math.log10(raw))
    base = 10 ** exp
    for m in (1, 2, 5, 10):
        if m * base >= raw:
            return float(m * base)
    return float(10 * base)


class PlanView(QtWidgets.QWidget):
    """Interaktiivinen pohjapiirros usean kerroksen tuella."""
    element_picked = QtCore.Signal(int, str, str)   # floor_idx, kind, id ("" = tyhjä)
    elements_boxed = QtCore.Signal(int, list)        # floor_idx, [(kind, id), ...]

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._models: list = []
        self._items: dict = {}
        self._hl_items: list = []

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
        self._view = _PlanGraphicsView(self._scene)
        self._view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._view.setTransformationAnchor(
            QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self._view._pick = self._on_pick
        self._view._box_pick = self._on_box
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
        self._items = {}          # (kind, id) -> QGraphicsItem (highlightia varten)
        self._hl_items = []
        flags = {f["id"] for f in flag_low_confidence(model)}

        # --- Laatta (lattia-footprint): hienovarainen ääriviiva pohjalle ---
        for s in getattr(model, "slabs", []) or []:
            if getattr(s, "slab_type", "") != "floor" or len(getattr(s, "boundary", []) or []) < 3:
                continue
            poly = QtGui.QPolygonF([QtCore.QPointF(x, -y) for x, y in s.boundary])
            pen = QtGui.QPen(QtGui.QColor(_SLAB_COLOR))
            pen.setCosmetic(True); pen.setWidthF(1.4)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            fill = QtGui.QColor(_SLAB_COLOR); fill.setAlpha(20)
            self._scene.addPolygon(poly, pen, QtGui.QBrush(fill)).setZValue(-1)

        # --- Huoneet: pehmeä täyttö + pinta-alachippi ---
        for i, sp in enumerate(getattr(model, "spaces", []) or []):
            poly = QtGui.QPolygonF([QtCore.QPointF(x, -y) for x, y in sp.boundary])
            fill = QtGui.QColor(_ROOM_FILLS[i % len(_ROOM_FILLS)])
            fill.setAlpha(38)
            self._scene.addPolygon(poly, QtGui.QPen(QtCore.Qt.PenStyle.NoPen),
                                   QtGui.QBrush(fill)).setZValue(0)
            area = _polygon_area(sp.boundary) / 1e6  # m²
            self._add_chip(f"{area:.1f} m²", poly.boundingRect().center())

        # --- Seinät: umpiviivat, pyöreä pää ---
        wall_pen = QtGui.QPen(QtGui.QColor(_WALL_COLOR))
        wall_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        wall_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        for w in getattr(model, "walls", []) or []:
            (x0, y0), (x1, y1) = w.axis[0], w.axis[1]
            th = max(float(w.thickness), 60.0)
            wall_pen.setWidthF(th)
            item = self._scene.addLine(x0, -y0, x1, -y1, wall_pen)
            item.setZValue(1)
            item.setData(0, ("wall", w.id))
            self._items[("wall", w.id)] = item
            if w.id in flags:
                self._flag_line(x0, -y0, x1, -y1, th)

        # --- Palkit: katkoviiva (yläpuolinen rakenne, plan-konventio) ---
        beam_pen = QtGui.QPen(QtGui.QColor(_BEAM_COLOR))
        beam_pen.setCosmetic(True); beam_pen.setWidthF(1.6)
        beam_pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        for b in getattr(model, "beams", []) or []:
            (x0, y0, *_), (x1, y1, *_) = b.axis[0], b.axis[1]
            item = self._scene.addLine(x0, -y0, x1, -y1, beam_pen)
            item.setZValue(2)
            item.setData(0, ("beam", b.id))
            self._items[("beam", b.id)] = item
            if b.id in flags:
                self._flag_line(x0, -y0, x1, -y1, 120.0)

        # --- Pilarit: umpitäyttö (poché) sijainnissa profiilin kokoisena ---
        for c in getattr(model, "columns", []) or []:
            cx, cy = c.location[0], -c.location[1]
            pw = max(float(c.profile.width), 120.0)
            pd = max(float(c.profile.depth), 120.0)
            pen = QtGui.QPen(QtGui.QColor(_COLUMN_EDGE)); pen.setCosmetic(True); pen.setWidthF(1.5)
            brush = QtGui.QBrush(QtGui.QColor(_COLUMN_FILL))
            if c.profile.shape == "circle":
                item = self._scene.addEllipse(cx - pw / 2, cy - pd / 2, pw, pd, pen, brush)
            else:
                item = self._scene.addRect(cx - pw / 2, cy - pd / 2, pw, pd, pen, brush)
            item.setZValue(3)
            item.setData(0, ("column", c.id))
            self._items[("column", c.id)] = item
            if c.id in flags:
                self._flag_rect(cx, cy, pw, pd)

        # --- Ovet / ikkunat: aukko seinään + symboli ---
        for op in getattr(model, "openings", []) or []:
            w = next((w for w in model.walls if w.id == op.wall_id), None)
            if not w:
                continue
            self._draw_opening(op, w, flagged=op.id in flags)

        # Rubber-band-valinta (maalaamalla): elementit valittavissa.
        for it in self._items.values():
            it.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        self._view.setSceneRect(self._scene.itemsBoundingRect().adjusted(-800, -800, 800, 800))
        self._view.fitInView(self._scene.itemsBoundingRect().adjusted(-400, -400, 400, 400),
                             QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self._view.viewport().update()

        nw = len(getattr(model, "walls", []) or [])
        ns = len(getattr(model, "spaces", []) or [])
        nd = sum(1 for o in getattr(model, "openings", []) or [] if o.opening_type == "door")
        nwin = sum(1 for o in getattr(model, "openings", []) or [] if o.opening_type != "door")
        nc = len(getattr(model, "columns", []) or [])
        nb = len(getattr(model, "beams", []) or [])
        parts = [f"{nw} seinää", f"{ns} huonetta", f"{nd} ovea", f"{nwin} ikkunaa"]
        if nc:
            parts.append(f"{nc} pilaria")
        if nb:
            parts.append(f"{nb} palkkia")
        self._stats.setText(" · ".join(parts))

    def _add_chip(self, text: str, center: QtCore.QPointF) -> None:
        chip = self._scene.addText(text)
        chip.setDefaultTextColor(QtGui.QColor(TEXT))
        f = chip.font(); f.setPointSize(10); f.setBold(True); chip.setFont(f)
        chip.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        br = chip.boundingRect()
        chip_path = QtGui.QPainterPath()
        chip_path.addRoundedRect(QtCore.QRectF(0, 0, br.width() + 14, br.height() + 6), 6, 6)
        bg = self._scene.addPath(
            chip_path,
            QtGui.QPen(QtCore.Qt.PenStyle.NoPen),
            QtGui.QBrush(QtGui.QColor(BG_PANEL)),
        )
        bg.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        bg.setPos(center.x() - br.width() / 2 - 7, center.y() - br.height() / 2 - 3)
        bg.setZValue(4)
        chip.setPos(center.x() - br.width() / 2, center.y() - br.height() / 2)
        chip.setZValue(5)

    # --- tarkistus-merkinnät (matala luottamus) -------------------------------

    def _flag_pen(self) -> QtGui.QPen:
        pen = QtGui.QPen(QtGui.QColor(_FLAG_COLOR))
        pen.setCosmetic(True); pen.setWidthF(2.2)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        return pen

    def _flag_line(self, x0: float, y0: float, x1: float, y1: float, width: float) -> None:
        pen = self._flag_pen()
        pen.setCosmetic(False); pen.setWidthF(width + 90)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        col = QtGui.QColor(_FLAG_COLOR); col.setAlpha(150); pen.setColor(col)
        self._scene.addLine(x0, y0, x1, y1, pen).setZValue(6)

    def _flag_rect(self, cx: float, cy: float, w: float, d: float) -> None:
        m = 130.0
        self._scene.addRect(cx - w / 2 - m, cy - d / 2 - m, w + 2 * m, d + 2 * m,
                            self._flag_pen()).setZValue(6)

    def _flag_dot(self, cx: float, cy: float, width: float) -> None:
        r = max(width / 2 + 120, 220)
        self._scene.addEllipse(cx - r, cy - r, 2 * r, 2 * r, self._flag_pen()).setZValue(6)

    def _on_pick(self, kind, elem_id) -> None:
        if not kind:
            self.clear_selection()
            self.element_picked.emit(-1, "", "")
            return
        self.highlight(kind, elem_id)
        fi = max(0, self._floor_combo.currentIndex())
        self.element_picked.emit(fi, kind, elem_id)

    def _on_box(self, pairs: list) -> None:
        self.highlight_many(pairs, center=False)
        fi = max(0, self._floor_combo.currentIndex())
        self.elements_boxed.emit(fi, pairs)

    def clear_selection(self) -> None:
        for it in self._hl_items:
            self._scene.removeItem(it)
        self._hl_items = []

    def highlight(self, kind: str, elem_id: str) -> None:
        """Korosta yksi valittu elementti (myös tarkistuslistasta klikattu)."""
        self.highlight_many([(kind, elem_id)], center=True)

    def highlight_many(self, pairs: list, center: bool = False) -> None:
        self.clear_selection()
        pen = QtGui.QPen(QtGui.QColor(ACCENT)); pen.setCosmetic(True); pen.setWidthF(2.5)
        rects = []
        for pair in pairs:
            item = self._items.get(tuple(pair))
            if item is None:
                continue
            r = item.sceneBoundingRect().adjusted(-180, -180, 180, 180)
            ring = self._scene.addRect(r, pen); ring.setZValue(7)
            self._hl_items.append(ring); rects.append(r)
        if center and rects:
            self._view.centerOn(rects[0].center())

    def _draw_opening(self, op, wall, flagged: bool = False) -> None:
        (x0, y0), (x1, y1) = wall.axis[0], wall.axis[1]
        # Scene-koordinaatit (y käännetty).
        p0 = QtCore.QPointF(x0, -y0); p1 = QtCore.QPointF(x1, -y1)
        L = math.hypot(p1.x() - p0.x(), p1.y() - p0.y()) or 1.0
        ux, uy = (p1.x() - p0.x()) / L, (p1.y() - p0.y()) / L
        nx, ny = -uy, ux
        width = float(getattr(op, "width", 0.0)) or 800.0
        t = float(op.position_along)
        cx, cy = p0.x() + ux * t, p0.y() + uy * t
        half = width / 2.0
        thick = max(float(wall.thickness), 60.0)

        # 1) Aukko: "pyyhi" seinä taustan värillä aukon kohdalta.
        gap = QtGui.QPen(QtGui.QColor(BG))
        gap.setWidthF(thick + 4)
        gap.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
        gline = self._scene.addLine(cx - ux * half, cy - uy * half,
                                    cx + ux * half, cy + uy * half, gap)
        gline.setZValue(2)
        gline.setData(0, (op.opening_type, op.id))
        self._items[(op.opening_type, op.id)] = gline
        if flagged:
            self._flag_dot(cx, cy, width)

        if op.opening_type == "door":
            # Ovilehti + avautumiskaari (neljännesympyrä saranasta).
            hx, hy = cx - ux * half, cy - uy * half          # sarana
            lx, ly = hx + nx * width, hy + ny * width          # lehden pää
            pen = QtGui.QPen(QtGui.QColor(_DOOR_COLOR), 0)
            pen.setCosmetic(True); pen.setWidthF(2.0)
            self._scene.addLine(hx, hy, lx, ly, pen).setZValue(3)
            # kaari: kierrä saranasta lehdestä (n) kohti aukkoa (u)
            path = QtGui.QPainterPath(QtCore.QPointF(lx, ly))
            steps = 14
            cross = nx * uy - ny * ux
            sign = 1.0 if cross > 0 else -1.0
            for k in range(1, steps + 1):
                a = sign * (math.pi / 2) * (k / steps)
                ca, sa = math.cos(a), math.sin(a)
                vx = nx * ca - ny * sa
                vy = nx * sa + ny * ca
                path.lineTo(hx + vx * width, hy + vy * width)
            arc = self._scene.addPath(path, pen)
            arc.setZValue(3)
        else:
            # Ikkuna: lasilinja aukon poikki (kaksi ohutta viivaa seinän suunnassa).
            pen = QtGui.QPen(QtGui.QColor(_WINDOW_COLOR), 0)
            pen.setCosmetic(True); pen.setWidthF(2.0)
            off = min(thick, 120.0) * 0.28
            for s in (-off, off):
                self._scene.addLine(cx - ux * half + nx * s, cy - uy * half + ny * s,
                                    cx + ux * half + nx * s, cy + uy * half + ny * s,
                                    pen).setZValue(3)


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

"""Immersiivinen panoraamatarkastus: skannerin 6 kuutiosivua per asema
stitchataan yhdeksi 360° panoraamaksi, jota katsellaan vapaasti hiirellä
(kuten Cintoon kuvakupla). Malli projisoidaan päälle. Liiku asemien välillä.

Vaatii E57:n jossa on images2D-kuvat (Matterport-skybox, Radikal). Renderöinnin
ydin (equirect-stitch + perspektiivi + malli-overlay) validoitu staattisesti.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim.gui.photo_view import (
    load_cameras, _wall_edges, _opening_edges, _column_edges,
)


def _qimage_to_np(jpeg: bytes) -> np.ndarray:
    img = QtGui.QImage.fromData(jpeg).convertToFormat(QtGui.QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)
    return buf[:, : w * 3].reshape(h, w, 3).copy()


def build_equirect(cams: list, H: int = 1024) -> np.ndarray:
    """6 kuutiosivua → equirect-panoraama (H, 2H, 3). Jokainen ekvirekti-pikseli:
    suuntavektori → se kuutiosivu jonka näkökenttään suunta osuu → näytteistä."""
    W = 2 * H
    yy, xx = np.mgrid[0:H, 0:W]
    lon = (xx / W) * 2 * np.pi - np.pi
    lat = np.pi / 2 - (yy / H) * np.pi
    d = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], -1).reshape(-1, 3)
    equi = np.zeros((H * W, 3), np.uint8)
    fil = np.zeros(H * W, bool)
    for c in cams:
        img = _qimage_to_np(c.jpeg())
        dc = d @ c.R
        z = dc[:, 2]
        m = (z > 1e-6) & (np.abs(dc[:, 0]) <= z) & (np.abs(dc[:, 1]) <= z) & (~fil)
        if not m.any():
            continue
        u = np.clip((c.ppx + c.fl * dc[m, 0] / (z[m] * c.pw)).astype(int), 0, img.shape[1] - 1)
        v = np.clip((c.ppy + c.fl * dc[m, 1] / (z[m] * c.ph_)).astype(int), 0, img.shape[0] - 1)
        equi[m] = img[v, u]
        fil[m] = True
    return equi.reshape(H, W, 3)


def _virtual_basis(yaw: float, pitch: float):
    fwd = np.array([np.cos(pitch) * np.cos(yaw), np.cos(pitch) * np.sin(yaw), np.sin(pitch)])
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up); rn = np.linalg.norm(right)
    right = right / rn if rn > 1e-6 else np.array([1.0, 0.0, 0.0])
    up2 = np.cross(right, fwd)
    Rv = np.stack([right, -up2, fwd], 1)   # maailma = Rv @ cam ; cam +Z=fwd +Y=alas
    return Rv


def perspective(equi: np.ndarray, yaw: float, pitch: float, fov_deg: float,
                ow: int, oh: int) -> np.ndarray:
    H, W = equi.shape[:2]
    f = (ow / 2) / np.tan(np.radians(fov_deg) / 2)
    Rv = _virtual_basis(yaw, pitch)
    px, py = np.meshgrid(np.arange(ow), np.arange(oh))
    ray = np.stack([(px - ow / 2) / f, (py - oh / 2) / f, np.ones_like(px, float)], -1).reshape(-1, 3)
    rw = ray @ Rv.T
    n = np.linalg.norm(rw, axis=1)
    lon = np.arctan2(rw[:, 1], rw[:, 0])
    lat = np.arcsin(np.clip(rw[:, 2] / n, -1, 1))
    sx = np.clip(((lon + np.pi) / (2 * np.pi) * W).astype(int), 0, W - 1)
    sy = np.clip(((np.pi / 2 - lat) / np.pi * H).astype(int), 0, H - 1)
    return equi[sy, sx].reshape(oh, ow, 3)


class _Loader(QtCore.QObject):
    done = QtCore.Signal(object, object)   # stations [(T, equirect)], cloud_pts
    failed = QtCore.Signal(str)

    def __init__(self, e57_path: str):
        super().__init__()
        self._path = e57_path

    def run(self):
        try:
            cams = load_cameras(self._path)
            if not cams:
                self.done.emit([], None)
                return
            groups = defaultdict(list)
            for c in cams:
                groups[tuple(np.round(c.T / 100).astype(int))].append(c)
            stations = []
            for key in sorted(groups):
                cs = groups[key]
                stations.append((cs[0].T, build_equirect(cs)))
            from scan2bim.core.geometry.loader import load_point_cloud
            P = np.asarray(load_point_cloud(Path(self._path)).points, np.float32)
            step = max(1, -(-len(P) // 3_000_000))
            cloud = np.ascontiguousarray(P[::step])
            self.done.emit(stations, cloud)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class PanoView(QtWidgets.QWidget):
    """360°-panoraama per asema + malli. Hiiri katsoo, asemanuolet liikkuvat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None; self._path = None
        self._stations: list = []; self._cloud = None
        self._idx = 0; self._yaw = 0.0; self._pitch = 0.0; self._fov = 90.0
        self._thread = None; self._loader = None; self._last_pos = None
        self._ow, self._oh = 1280, 800

        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        bar = QtWidgets.QHBoxLayout(); bar.setContentsMargins(10, 8, 10, 8)
        self._load_btn = QtWidgets.QPushButton("Lataa panoraamat")
        self._load_btn.clicked.connect(self._start_load); bar.addWidget(self._load_btn)
        self._prev = QtWidgets.QPushButton("◀ asema"); self._prev.setEnabled(False)
        self._prev.clicked.connect(lambda: self._station(-1)); bar.addWidget(self._prev)
        self._next = QtWidgets.QPushButton("asema ▶"); self._next.setEnabled(False)
        self._next.clicked.connect(lambda: self._station(1)); bar.addWidget(self._next)
        self._model_chk = QtWidgets.QCheckBox("Malli päällä"); self._model_chk.setChecked(True)
        self._model_chk.setEnabled(False); self._model_chk.toggled.connect(self._render)
        bar.addWidget(self._model_chk)
        self._info = QtWidgets.QLabel("Aja konversio ja avaa tämä välilehti.")
        bar.addWidget(self._info); bar.addStretch()
        hint = QtWidgets.QLabel("Hiiri: katso ympäri · rulla: zoom")
        hint.setStyleSheet("color:#8a8f98;"); bar.addWidget(hint)
        lay.addLayout(bar)
        self._label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:#111;"); self._label.setMinimumSize(400, 300)
        lay.addWidget(self._label, stretch=1)
        self._pixmap = None

    # -- API --
    def set_source(self, model: dict, cloud_path: str):
        self._model = model
        if cloud_path != self._path:
            self._path = cloud_path; self._stations = []; self._cloud = None
            self._pixmap = None; self._label.clear()
            for w in (self._prev, self._next, self._model_chk):
                w.setEnabled(False)
            if Path(cloud_path).suffix.lower() == ".e57":
                self._load_btn.setEnabled(True); self._info.setText("Paina 'Lataa panoraamat'.")
            else:
                self._load_btn.setEnabled(False)
                self._info.setText("Ei panoraamoja (vain E57-skannissa on kuvat).")
        elif self._stations:
            self._render()

    # -- lataus --
    def _start_load(self):
        if not self._path or self._thread is not None:
            return
        if not Path(self._path).exists():
            self._info.setText("Pilvitiedostoa ei löydy."); return
        self._load_btn.setEnabled(False); self._info.setText("Ladataan panoraamoja…")
        self._thread = QtCore.QThread(self); self._loader = _Loader(self._path)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._on_loaded); self._loader.failed.connect(self._on_failed)
        self._thread.start()

    def _stop(self):
        if self._thread is not None:
            self._thread.quit(); self._thread.wait(); self._thread = None; self._loader = None

    def _on_failed(self, msg):
        self._stop(); self._info.setText(f"Lataus epäonnistui: {msg}"); self._load_btn.setEnabled(True)

    def _on_loaded(self, stations, cloud):
        self._stop(); self._stations = stations; self._cloud = cloud
        if not stations:
            self._info.setText("Ei kuvia tässä E57:ssä."); return
        self._idx = 0; self._yaw = 0.0; self._pitch = 0.0
        for w in (self._prev, self._next, self._model_chk):
            w.setEnabled(True)
        self._render()

    def _station(self, d):
        if not self._stations:
            return
        self._idx = (self._idx + d) % len(self._stations)
        self._render()

    # -- hiiri --
    def mousePressEvent(self, ev): self._last_pos = ev.position()
    def mouseReleaseEvent(self, ev): self._last_pos = None

    def mouseMoveEvent(self, ev):
        if self._last_pos is None or not self._stations:
            return
        p = ev.position()
        self._yaw -= (p.x() - self._last_pos.x()) * 0.005
        self._pitch = float(np.clip(self._pitch + (p.y() - self._last_pos.y()) * 0.005,
                                    -np.pi / 2 + 0.05, np.pi / 2 - 0.05))
        self._last_pos = p; self._render()

    def wheelEvent(self, ev):
        if not self._stations:
            return
        self._fov = float(np.clip(self._fov - ev.angleDelta().y() / 60.0, 40.0, 110.0))
        self._render()

    # -- piirto --
    def _render(self):
        if not self._stations:
            return
        T, equi = self._stations[self._idx]
        out = perspective(equi, self._yaw, self._pitch, self._fov, self._ow, self._oh)
        img = QtGui.QImage(np.ascontiguousarray(out).data, self._ow, self._oh,
                           3 * self._ow, QtGui.QImage.Format.Format_RGB888).copy()
        pm = QtGui.QPixmap.fromImage(img)
        if self._model_chk.isChecked() and self._model is not None:
            self._draw_model(pm, T)
        self._pixmap = pm
        self._info.setText(f"asema {self._idx + 1}/{len(self._stations)}  "
                           f"(fov {self._fov:.0f}°)  · syaani=seinä punainen=aukko keltainen=pilari")
        self._update_label()

    def _draw_model(self, pm, T):
        Rv = _virtual_basis(self._yaw, self._pitch)
        f = (self._ow / 2) / np.tan(np.radians(self._fov) / 2)
        wall_by_id = {w["id"]: w for w in self._model["walls"]}
        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        def proj(P):
            dc = (np.asarray(P, float) - T) @ Rv
            return dc

        def draw(edges, color, width):
            pen = QtGui.QPen(color); pen.setWidth(width); painter.setPen(pen)
            for a, b in edges:
                a = np.asarray(a, float); b = np.asarray(b, float)
                prev = None
                for t in np.linspace(0.0, 1.0, 24):
                    p = a + t * (b - a); dc = proj(p)
                    cur = None
                    if dc[2] > 50.0:
                        u = self._ow / 2 + f * dc[0] / dc[2]
                        v = self._oh / 2 + f * dc[1] / dc[2]
                        if -self._ow < u < 2 * self._ow and -self._oh < v < 2 * self._oh:
                            cur = QtCore.QPointF(u, v)
                    if prev is not None and cur is not None:
                        painter.drawLine(prev, cur)
                    prev = cur

        for w in self._model["walls"]:
            draw(_wall_edges(w), QtGui.QColor(0, 200, 255), 2)
        for c in self._model.get("columns", []):
            draw(_column_edges(c), QtGui.QColor(255, 220, 0), 2)
        for op in self._model.get("openings", []):
            draw(_opening_edges(op, wall_by_id), QtGui.QColor(255, 40, 40), 4)
        painter.end()

    def _update_label(self):
        if self._pixmap is None:
            return
        self._label.setPixmap(self._pixmap.scaled(
            self._label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e); self._update_label()

"""Upotettu 3D-tarkastusnäkymä: pistepilvi + malli samassa välilehdessä.

pyqtgraph.opengl (MIT) — upotettava QWidget. Hiiri kääntää katseen, WASD+QE
lentää (Shift = nopeampi). Pilvi ladataan taustasäikeessä ettei GUI jäädy.
Näkymämoodit: Väri / Residuaali (punainen = malli ei kata) / Vain puuttuvat.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtWidgets

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
import pyqtgraph.opengl as gl  # noqa: E402
from pyqtgraph import Vector  # noqa: E402


class _FlyView(gl.GLViewWidget):
    """GLViewWidget + WASD/QE-lentokamera. Hiiri kääntää (orbit), näppäimet
    liikuttavat kameraa katseen suuntaan → pelimäinen navigointi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._keys: set[int] = set()
        self._last_pos = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)
        self._timer.start()

    def keyPressEvent(self, e):
        self._keys.add(e.key())

    def keyReleaseEvent(self, e):
        if not e.isAutoRepeat():
            self._keys.discard(e.key())

    def focusOutEvent(self, e):
        self._keys.clear()
        super().focusOutEvent(e)

    # -- FPS-hiirikatse: raahaus kääntää katsesuuntaa, kamera pysyy paikallaan --
    def mousePressEvent(self, ev):
        self._last_pos = ev.position()
        self.setFocus()

    def mouseReleaseEvent(self, ev):
        self._last_pos = None

    def mouseMoveEvent(self, ev):
        if self._last_pos is None:
            self._last_pos = ev.position()
            return
        p = ev.position()
        dx = p.x() - self._last_pos.x(); dy = p.y() - self._last_pos.y()
        self._last_pos = p
        cam = self.cameraPosition()
        az = self.opts["azimuth"] - dx * 0.16
        el = float(np.clip(self.opts["elevation"] - dy * 0.16, -89.0, 89.0))
        ar, er = np.radians(az), np.radians(el)
        u = Vector(np.cos(er) * np.cos(ar), np.cos(er) * np.sin(ar), np.sin(er))
        self.opts["azimuth"] = az
        self.opts["elevation"] = el
        self.opts["center"] = cam - u * self.opts["distance"]
        self.update()

    def _step(self):
        if not self._keys:
            return
        Q = QtCore.Qt.Key
        cam = self.cameraPosition(); center = self.opts["center"]
        # täysi 3D-katsesuunta → W/S lentää minne katsoo (myös ylös/alas)
        fwd = np.array([center.x() - cam.x(), center.y() - cam.y(), center.z() - cam.z()])
        nrm = np.linalg.norm(fwd)
        fwd = fwd / nrm if nrm > 1e-6 else np.array([1.0, 0.0, 0.0])
        right = np.array([fwd[1], -fwd[0], 0.0])           # sivuaskel pysyy vaakana
        rnrm = np.linalg.norm(right)
        right = right / rnrm if rnrm > 1e-6 else np.array([1.0, 0.0, 0.0])
        up = np.array([0.0, 0.0, 1.0])                     # Q/E maailman pystyssä
        move = np.zeros(3)
        if Q.Key_W in self._keys: move += fwd
        if Q.Key_S in self._keys: move -= fwd
        if Q.Key_D in self._keys: move += right
        if Q.Key_A in self._keys: move -= right
        if Q.Key_E in self._keys: move += up
        if Q.Key_Q in self._keys: move -= up
        if not move.any():
            return
        step = max(self.opts["distance"] * 0.005, 25.0)
        if QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            step *= 3.5
        self.opts["center"] = center + Vector(*(move * step))
        self.update()


# --- pisteiden luokittelu: selittääkö malli pisteen -------------------------

def classify_explained(P: np.ndarray, model: dict, tol: float = 200.0) -> np.ndarray:
    P = np.asarray(P, float)
    expl = np.zeros(len(P), bool)
    xy, z = P[:, :2], P[:, 2]
    for w in model["walls"]:
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        d = np.array([x1 - x0, y1 - y0]); L = float(np.hypot(*d))
        if L < 1:
            continue
        u = d / L; n = np.array([-u[1], u[0]])
        rel = xy - np.array([x0, y0]); along = rel @ u; perp = rel @ n
        z0 = w.get("z_min", 0.0); z1 = z0 + w["height"]; th = w.get("thickness", 100.0)
        expl |= ((np.abs(perp) < th / 2 + tol) & (along >= -tol) & (along <= L + tol)
                 & (z >= z0 - tol) & (z <= z1 + tol))
    for c in model.get("columns", []):
        cx, cy = c["location"]; z0 = c["base_z"]; z1 = z0 + c["height"]; pr = c["profile"]
        expl |= ((np.abs(xy[:, 0] - cx) < pr["width"] / 2 + tol)
                 & (np.abs(xy[:, 1] - cy) < pr["depth"] / 2 + tol)
                 & (z >= z0 - tol) & (z <= z1 + tol))
    for b in model.get("beams", []):
        a, cc = np.array(b["axis"][0], float), np.array(b["axis"][1], float)
        d = cc - a; L = float(np.linalg.norm(d[:2]))
        if L < 1:
            continue
        u = d[:2] / L; nn = np.array([-u[1], u[0]])
        rel = xy - a[:2]; along = rel @ u; perp = rel @ nn
        pr = b["profile"]; zc = (a[2] + cc[2]) / 2
        expl |= ((np.abs(perp) < pr["width"] / 2 + tol) & (along >= -tol) & (along <= L + tol)
                 & (np.abs(z - zc) < pr["height"] / 2 + tol))
    return expl


# --- mallin laatikko-mesh (verteksit + kolmiot) -----------------------------

_BOX_FACES = np.array([
    [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 4, 5], [0, 5, 1],
    [1, 5, 6], [1, 6, 2], [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
], dtype=int)


def _box_verts(center, size, angle):
    sx, sy, sz = (max(float(s), 1.0) for s in size)
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    v = np.array([[-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
                  [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz]])
    ca, sa = np.cos(angle), np.sin(angle)
    R = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
    return v @ R.T + np.asarray(center)


def _accumulate_boxes(boxes):
    """boxes: [(center,size,angle)] -> (Vx3, Fx3) yhdistettynä."""
    V, F = [], []
    for i, (center, size, angle) in enumerate(boxes):
        V.append(_box_verts(center, size, angle))
        F.append(_BOX_FACES + i * 8)
    if not V:
        return None, None
    return np.vstack(V), np.vstack(F)


def _model_boxes(model):
    walls, cols, beams = [], [], []
    for w in model["walls"]:
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        dx, dy = x1 - x0, y1 - y0; L = float(np.hypot(dx, dy))
        if L < 1:
            continue
        z0 = w.get("z_min", 0.0); h = w["height"]
        walls.append((((x0 + x1) / 2, (y0 + y1) / 2, z0 + h / 2),
                      (L, max(w.get("thickness", 100.0), 40.0), h), float(np.arctan2(dy, dx))))
    for c in model.get("columns", []):
        cx, cy = c["location"]; z0 = c["base_z"]; h = c["height"]; pr = c["profile"]
        cols.append(((cx, cy, z0 + h / 2), (pr["width"], pr["depth"], h), 0.0))
    for b in model.get("beams", []):
        a, cc = np.array(b["axis"][0], float), np.array(b["axis"][1], float)
        d = cc - a; L = float(np.linalg.norm(d[:2]))
        if L < 1:
            continue
        pr = b["profile"]
        beams.append((tuple((a + cc) / 2), (L, pr["width"], pr["height"]), float(np.arctan2(d[1], d[0]))))
    return walls, cols, beams


def _opening_segments(model):
    wall_by_id = {w["id"]: w for w in model["walls"]}
    segs = []
    for op in model.get("openings", []):
        w = wall_by_id.get(op["wall_id"])
        if not w:
            continue
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        d = np.array([x1 - x0, y1 - y0]); L = np.linalg.norm(d)
        if L < 1:
            continue
        u = d / L; a0 = op["position_along"]; a1 = a0 + op["width"]
        zf = w.get("z_min", 0.0); z0 = zf + op["sill_height"]; z1 = z0 + op["opening_height"]
        pa = np.array([x0, y0]) + u * a0; pb = np.array([x0, y0]) + u * a1
        A = [pa[0], pa[1], z0]; B = [pb[0], pb[1], z0]
        C = [pb[0], pb[1], z1]; D = [pa[0], pa[1], z1]
        segs += [A, B, B, C, C, D, D, A]
    return np.array(segs, float) if segs else None


# --- taustalatain -----------------------------------------------------------

class _Loader(QtCore.QObject):
    done = QtCore.Signal(object, object, object)  # Ps_raw, rgb, offset
    failed = QtCore.Signal(str)

    def __init__(self, cloud_path: str, max_pts: int):
        super().__init__()
        self._path = cloud_path; self._max = max_pts

    def run(self) -> None:
        try:
            from scan2bim.core.geometry.loader import load_point_cloud
            cloud = load_point_cloud(Path(self._path))
            P = np.asarray(cloud.points, dtype=np.float32)
            step = max(1, len(P) // self._max)
            Ps = np.ascontiguousarray(P[::step])
            offset = Ps.mean(axis=0)
            if cloud.has_colors():
                rgb = np.asarray(cloud.colors, dtype=np.float32)[::step]
            else:
                rgb = np.full((len(Ps), 3), 0.6, np.float32)
            self.done.emit(Ps, np.ascontiguousarray(rgb), offset)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class InspectView(QtWidgets.QWidget):
    """3D-välilehti: pilvi + malli. Hiiri kääntää, WASD+QE lentää."""

    _MODES = ["Väri", "Residuaali", "Vain puuttuvat"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: dict | None = None
        self._cloud_path: str | None = None
        self._thread = None
        self._loader = None
        # ladattu pilvi (välimuistissa → mallin muutos ei vaadi uudelleenlatausta)
        self._Ps = None; self._rgb = None; self._offset = None; self._pts = None
        self._rgba = None; self._res = None; self._expl = None
        self._scatter = None; self._grid = None
        self._model_items: list = []

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 8)
        self._load_btn = QtWidgets.QPushButton("Näytä pistepilvi")
        self._load_btn.clicked.connect(self._start_load)
        bar.addWidget(self._load_btn)
        bar.addWidget(QtWidgets.QLabel("Näkymä:"))
        self._mode = QtWidgets.QComboBox()
        self._mode.addItems(self._MODES)
        self._mode.setEnabled(False)
        self._mode.currentIndexChanged.connect(lambda _i: self._refresh_scatter())
        bar.addWidget(self._mode)
        self._info = QtWidgets.QLabel("Aja konversio ja avaa tämä välilehti.")
        bar.addWidget(self._info)
        bar.addStretch()
        hint = QtWidgets.QLabel("Hiiri: käännä · WASD+QE: liiku · Shift: nopeampi")
        hint.setStyleSheet("color:#8a8f98;")
        bar.addWidget(hint)
        lay.addLayout(bar)

        self._view = _FlyView()
        self._view.setBackgroundColor((18, 20, 24))
        lay.addWidget(self._view, stretch=1)

    # -- julkinen API --
    def set_source(self, model: dict, cloud_path: str) -> None:
        """Aseta tarkastettava malli + pilvipolku."""
        self._model = model
        if cloud_path == self._cloud_path and self._Ps is not None:
            self._apply_model()          # sama pilvi ladattu → päivitä vain malli
            return
        self._cloud_path = cloud_path
        self._Ps = None; self._pts = None
        self._view.clear()
        self._scatter = None; self._grid = None; self._model_items = []
        self._mode.setEnabled(False)
        self._load_btn.setEnabled(True)
        self._info.setText("Paina 'Näytä pistepilvi'.")

    # -- lataus --
    def _start_load(self) -> None:
        if not self._model or not self._cloud_path or self._thread is not None:
            return
        if not Path(self._cloud_path).exists():
            self._info.setText("Pilvitiedostoa ei löydy — tarkastus vaatii alkuperäisen skannin.")
            return
        self._load_btn.setEnabled(False)
        self._info.setText("Ladataan pistepilveä…")
        self._thread = QtCore.QThread(self)
        self._loader = _Loader(self._cloud_path, 4_000_000)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._thread.start()

    def _stop_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit(); self._thread.wait()
            self._thread = None; self._loader = None

    def _on_failed(self, msg: str) -> None:
        self._stop_thread()
        self._info.setText(f"Lataus epäonnistui: {msg}")
        self._load_btn.setEnabled(True)

    def _on_loaded(self, Ps, rgb, offset) -> None:
        self._stop_thread()
        self._Ps = Ps; self._rgb = rgb; self._offset = offset
        self._rgba = np.column_stack([rgb, np.ones(len(rgb), np.float32)])
        self._pts = (Ps - offset).astype(np.float32)
        # perspektiivikoko (maailmayksikkö mm): lähellä pisteet suurenevat →
        # pinnat täyttyvät valokuvamaisiksi kun navigoi lähelle
        self._scatter = gl.GLScatterPlotItem(pos=self._pts, color=self._rgba, size=16.0, pxMode=False)
        self._scatter.setGLOptions("opaque")
        self._view.addItem(self._scatter)
        # pohjaruudukko orientaatioon
        lo = self._pts.min(axis=0); hi = self._pts.max(axis=0)
        ext = float(max(hi[0] - lo[0], hi[1] - lo[1]))
        self._grid = gl.GLGridItem()
        self._grid.setSize(ext * 1.2, ext * 1.2)
        self._grid.setSpacing(1000, 1000)                 # 1 m ruudukko
        self._grid.translate((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        self._grid.setGLOptions("opaque")
        self._view.addItem(self._grid)
        span = float(np.linalg.norm(hi - lo))
        self._view.setCameraPosition(distance=max(span * 0.55, 1000.0))
        self._mode.setEnabled(True)
        self._apply_model()

    # -- mallin piirto + residuaali (välimuistin pisteillä, ei uudelleenlatausta) --
    def _apply_model(self) -> None:
        if self._Ps is None or self._model is None:
            return
        for it in self._model_items:
            self._view.removeItem(it)
        self._model_items = []
        off = self._offset
        walls, cols, beams = _model_boxes(self._model)
        for boxes, color in ((walls, (0.0, 0.75, 1.0, 0.5)),
                             (cols, (1.0, 0.8, 0.0, 0.55)),
                             (beams, (0.1, 0.85, 0.2, 0.55))):
            V, F = _accumulate_boxes(boxes)
            if V is None:
                continue
            md = gl.MeshData(vertexes=(V - off).astype(np.float32), faces=F)
            mesh = gl.GLMeshItem(meshdata=md, smooth=False, color=color,
                                 shader="shaded", glOptions="translucent")
            self._view.addItem(mesh); self._model_items.append(mesh)
        segs = _opening_segments(self._model)
        if segs is not None:
            line = gl.GLLinePlotItem(pos=(segs - off).astype(np.float32),
                                     color=(1.0, 0.1, 0.1, 1.0), width=3.0, mode="lines")
            line.setGLOptions("opaque")
            self._view.addItem(line); self._model_items.append(line)
        # residuaaliluokittelu (talletetaan; väritys näkymämoodin mukaan)
        self._expl = classify_explained(self._Ps, self._model)
        res = np.tile(np.array([0.95, 0.12, 0.12, 1.0], np.float32), (len(self._Ps), 1))
        res[self._expl, :3] = self._rgb[self._expl] * 0.3     # selitetty himmeäksi → punainen erottuu
        self._res = res
        miss = int((~self._expl).sum())
        self._info.setText(f"{len(self._Ps)} pistettä · kattamatta {miss} "
                           "· syaani=seinä keltainen=pilari vihreä=palkki punainen=aukko")
        self._refresh_scatter()

    def _refresh_scatter(self) -> None:
        if self._scatter is None or self._pts is None:
            return
        mode = self._mode.currentIndex()
        if mode == 0:                                          # Väri
            self._scatter.setData(pos=self._pts, color=self._rgba, size=16.0, pxMode=False)
        elif mode == 1:                                        # Residuaali (kaikki)
            self._scatter.setData(pos=self._pts, color=self._res, size=16.0, pxMode=False)
        else:                                                  # Vain puuttuvat
            m = ~self._expl if self._expl is not None else np.ones(len(self._pts), bool)
            self._scatter.setData(pos=self._pts[m], color=self._res[m], size=28.0, pxMode=False)

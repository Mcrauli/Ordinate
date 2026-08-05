"""Valokuvatarkistus: skannerin oikeat kalibroidut valokuvat, joiden PÄÄLLE
detektoitu malli projisoidaan. Näin näkee suoraan "kuvia katsomalla" osuuko
seinä/aukko/pilari siihen mitä kamera näki (E57:n sisäiset pinhole-kuvat,
esim. Matterport-skybox). Malli piilotetaan lähemmän pinnan taakse
(syvyyskulku pistepilvestä), jotta osuvuus on rehellinen.

Vaatii E57:n jossa on images2D-kuvat. Muille pilville: "ei valokuvia".
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets


# ---------------------------------------------------------------------------
# Kamera + projektio (E57 pinhole)
# ---------------------------------------------------------------------------

def _quat_to_R(w, x, y, z):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


class _Camera:
    def __init__(self, node):
        ph = node["pinholeRepresentation"]
        self.w = ph["imageWidth"].value(); self.h = ph["imageHeight"].value()
        self.fl = ph["focalLength"].value()
        self.pw = ph["pixelWidth"].value(); self.ph_ = ph["pixelHeight"].value()
        self.ppx = ph["principalPointX"].value(); self.ppy = ph["principalPointY"].value()
        pose = node["pose"]; rot, tr = pose["rotation"], pose["translation"]
        q = [rot[k].value() for k in ("w", "x", "y", "z")]
        self.R = _quat_to_R(*q)
        self.T = np.array([tr[k].value() for k in ("x", "y", "z")]) * 1000.0
        self.name = node["name"].value()
        blob = ph["jpegImage"]; n = blob.byteCount(); buf = bytearray(n)
        blob.read(buf, 0, n); self._jpeg = bytes(buf)
        self._depth = None; self._cell = 8

    def jpeg(self) -> bytes:
        return self._jpeg

    def to_cam(self, P):
        return (np.asarray(P, float) - self.T) @ self.R

    def project(self, P):
        Pc = self.to_cam(np.atleast_2d(P)); zc = Pc[:, 2]
        front = zc > 1.0
        u = self.ppx + self.fl * Pc[:, 0] / (zc * self.pw)
        v = self.ppy + self.fl * Pc[:, 1] / (zc * self.ph_)
        return np.column_stack([u, v]), front

    def build_depth(self, cloud_pts):
        uv, front = self.project(cloud_pts)
        zc = self.to_cam(cloud_pts)[:, 2]
        u, v = uv[:, 0], uv[:, 1]
        ok = front & (u >= 0) & (u < self.w) & (v >= 0) & (v < self.h)
        gw = int(np.ceil(self.w / self._cell)); gh = int(np.ceil(self.h / self._cell))
        buf = np.full((gh, gw), np.inf)
        np.minimum.at(buf, ((v[ok] / self._cell).astype(int), (u[ok] / self._cell).astype(int)), zc[ok])
        self._depth = buf

    def occluded(self, p, margin=250.0):
        if self._depth is None:
            return False
        Pc = self.to_cam(p[None])[0]
        if Pc[2] <= 1.0:
            return True
        u = self.ppx + self.fl * Pc[0] / (Pc[2] * self.pw)
        v = self.ppy + self.fl * Pc[1] / (Pc[2] * self.ph_)
        gi = int(v / self._cell); gj = int(u / self._cell)
        if gi < 0 or gj < 0 or gi >= self._depth.shape[0] or gj >= self._depth.shape[1]:
            return False
        d = self._depth[gi, gj]
        return bool(np.isfinite(d) and Pc[2] > d + margin)


def load_cameras(e57_path: str) -> list[_Camera]:
    import pye57
    f = pye57.E57(str(e57_path))
    root = f.root
    if "images2D" not in [c.elementName() for c in root]:
        return []
    im = root["images2D"]
    cams = []
    for i in range(len(im)):
        try:
            cams.append(_Camera(im[i]))
        except Exception:  # noqa: BLE001,PERF203
            continue
    return cams


# ---------------------------------------------------------------------------
# Mallin reunat (3D-janat)
# ---------------------------------------------------------------------------

def _wall_edges(w):
    (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
    z0 = w.get("z_min", 0.0); z1 = z0 + w["height"]
    a = np.array([x0, y0, z0]); b = np.array([x1, y1, z0])
    c = np.array([x1, y1, z1]); d = np.array([x0, y0, z1])
    return [(a, b), (b, c), (c, d), (d, a)]


def _opening_edges(op, wall_by_id):
    w = wall_by_id.get(op["wall_id"])
    if w is None:
        return []
    (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
    d = np.array([x1 - x0, y1 - y0]); L = np.linalg.norm(d)
    if L < 1:
        return []
    u = d / L; a0 = op["position_along"]; a1 = a0 + op["width"]
    zf = w.get("z_min", 0.0); z0 = zf + op["sill_height"]; z1 = z0 + op["opening_height"]
    pa = np.array([x0, y0]) + u * a0; pb = np.array([x0, y0]) + u * a1
    A = np.array([pa[0], pa[1], z0]); B = np.array([pb[0], pb[1], z0])
    C = np.array([pb[0], pb[1], z1]); D = np.array([pa[0], pa[1], z1])
    return [(A, B), (B, C), (C, D), (D, A)]


def _column_edges(c):
    x, y = c["location"]; z0 = c["base_z"]; z1 = z0 + c["height"]
    pr = c["profile"]; wx = pr["width"] / 2; wy = pr["depth"] / 2
    cs = [(-wx, -wy), (wx, -wy), (wx, wy), (-wx, wy)]
    edges = []
    for i in range(4):
        cx, cy = cs[i]; nx, ny = cs[(i + 1) % 4]
        edges.append((np.array([x + cx, y + cy, z0]), np.array([x + nx, y + ny, z0])))
        edges.append((np.array([x + cx, y + cy, z1]), np.array([x + nx, y + ny, z1])))
        edges.append((np.array([x + cx, y + cy, z0]), np.array([x + cx, y + cy, z1])))
    return edges


# ---------------------------------------------------------------------------
# Taustalatain (kamerat + harva pilvi syvyyskulkuun)
# ---------------------------------------------------------------------------

class _Loader(QtCore.QObject):
    done = QtCore.Signal(object, object)   # cams, cloud_pts (tai None)
    failed = QtCore.Signal(str)

    def __init__(self, e57_path: str):
        super().__init__()
        self._path = e57_path

    def run(self):
        try:
            cams = load_cameras(self._path)
            pts = None
            if cams:
                from scan2bim.core.geometry.loader import load_point_cloud
                P = np.asarray(load_point_cloud(Path(self._path)).points, np.float32)
                step = max(1, len(P) // 4_000_000)
                pts = np.ascontiguousarray(P[::step])
            self.done.emit(cams, pts)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class PhotoView(QtWidgets.QWidget):
    """Skannerin valokuvat + malli projisoituna. Selaa nuolilla."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None; self._path = None
        self._cams: list[_Camera] = []; self._cloud = None
        self._idx = 0; self._thread = None; self._loader = None
        self._depth_built: set[int] = set()

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        bar = QtWidgets.QHBoxLayout(); bar.setContentsMargins(10, 8, 10, 8)
        self._load_btn = QtWidgets.QPushButton("Lataa valokuvat")
        self._load_btn.clicked.connect(self._start_load); bar.addWidget(self._load_btn)
        self._prev = QtWidgets.QPushButton("◀"); self._prev.setFixedWidth(40)
        self._prev.clicked.connect(lambda: self._step(-1)); self._prev.setEnabled(False)
        bar.addWidget(self._prev)
        self._next = QtWidgets.QPushButton("▶"); self._next.setFixedWidth(40)
        self._next.clicked.connect(lambda: self._step(1)); self._next.setEnabled(False)
        bar.addWidget(self._next)
        self._model_chk = QtWidgets.QCheckBox("Malli päällä"); self._model_chk.setChecked(True)
        self._model_chk.setEnabled(False); self._model_chk.toggled.connect(self._render)
        bar.addWidget(self._model_chk)
        self._occ_chk = QtWidgets.QCheckBox("Syvyyskulku"); self._occ_chk.setChecked(True)
        self._occ_chk.setEnabled(False); self._occ_chk.toggled.connect(self._render)
        bar.addWidget(self._occ_chk)
        self._info = QtWidgets.QLabel("Aja konversio ja avaa tämä välilehti.")
        bar.addWidget(self._info); bar.addStretch()
        lay.addLayout(bar)

        self._label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background:#111;")
        self._label.setMinimumSize(400, 300)
        lay.addWidget(self._label, stretch=1)
        self._pixmap = None

    def set_source(self, model: dict, cloud_path: str):
        self._model = model
        if cloud_path != self._path:
            self._path = cloud_path
            self._cams = []; self._cloud = None; self._depth_built = set()
            self._pixmap = None; self._label.clear()
            self._prev.setEnabled(False); self._next.setEnabled(False)
            self._model_chk.setEnabled(False); self._occ_chk.setEnabled(False)
            ext = Path(cloud_path).suffix.lower()
            if ext == ".e57":
                self._load_btn.setEnabled(True)
                self._info.setText("Paina 'Lataa valokuvat'.")
            else:
                self._load_btn.setEnabled(False)
                self._info.setText("Ei valokuvia (vain E57-skannissa on kalibroidut kuvat).")
        elif self._cams:
            self._depth_built = set()   # malli muuttui → piirrä uudelleen
            self._render()

    # -- lataus --
    def _start_load(self):
        if not self._path or self._thread is not None:
            return
        self._load_btn.setEnabled(False)
        self._info.setText("Ladataan valokuvia…")
        self._thread = QtCore.QThread(self)
        self._loader = _Loader(self._path)
        self._loader.moveToThread(self._thread)
        self._thread.started.connect(self._loader.run)
        self._loader.done.connect(self._on_loaded)
        self._loader.failed.connect(self._on_failed)
        self._thread.start()

    def _stop_thread(self):
        if self._thread is not None:
            self._thread.quit(); self._thread.wait()
            self._thread = None; self._loader = None

    def _on_failed(self, msg):
        self._stop_thread()
        self._info.setText(f"Lataus epäonnistui: {msg}")
        self._load_btn.setEnabled(True)

    def _on_loaded(self, cams, cloud):
        self._stop_thread()
        self._cams = cams; self._cloud = cloud
        if not cams:
            self._info.setText("Ei valokuvia tässä E57:ssä.")
            return
        self._idx = 0
        for w in (self._prev, self._next, self._model_chk, self._occ_chk):
            w.setEnabled(True)
        self._render()

    def _step(self, d):
        if not self._cams:
            return
        self._idx = (self._idx + d) % len(self._cams)
        self._render()

    # -- piirto --
    def _render(self):
        if not self._cams:
            return
        cam = self._cams[self._idx]
        img = QtGui.QImage.fromData(cam.jpeg())
        pm = QtGui.QPixmap.fromImage(img)
        if self._model_chk.isChecked() and self._model is not None:
            occ = self._occ_chk.isChecked() and self._cloud is not None
            if occ and self._idx not in self._depth_built:
                cam.build_depth(self._cloud); self._depth_built.add(self._idx)
            self._draw_model(pm, cam, occ)
        self._pixmap = pm
        self._info.setText(f"kuva {self._idx + 1}/{len(self._cams)}  ({cam.name})  "
                           "· syaani=seinä punainen=aukko keltainen=pilari")
        self._update_label()

    def _draw_model(self, pm, cam, occ):
        wall_by_id = {w["id"]: w for w in self._model["walls"]}
        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        def draw(edges, color, width):
            pen = QtGui.QPen(color); pen.setWidth(width); painter.setPen(pen)
            for a, b in edges:
                a = np.asarray(a, float); b = np.asarray(b, float)
                prev = None
                for t in np.linspace(0.0, 1.0, 20):
                    p = a + t * (b - a)
                    cur = None
                    if not (occ and cam.occluded(p)):
                        Pc = cam.to_cam(p[None])[0]
                        if Pc[2] > 50.0:
                            u = cam.ppx + cam.fl * Pc[0] / (Pc[2] * cam.pw)
                            v = cam.ppy + cam.fl * Pc[1] / (Pc[2] * cam.ph_)
                            if -cam.w < u < 2 * cam.w and -cam.h < v < 2 * cam.h:
                                cur = QtCore.QPointF(u, v)
                    if prev is not None and cur is not None:
                        painter.drawLine(prev, cur)
                    prev = cur

        for w in self._model["walls"]:
            draw(_wall_edges(w), QtGui.QColor(0, 200, 255), 3)
        for c in self._model.get("columns", []):
            draw(_column_edges(c), QtGui.QColor(255, 220, 0), 3)
        for op in self._model.get("openings", []):
            draw(_opening_edges(op, wall_by_id), QtGui.QColor(255, 40, 40), 5)
        painter.end()

    def _update_label(self):
        if self._pixmap is None:
            return
        self._label.setPixmap(self._pixmap.scaled(
            self._label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_label()

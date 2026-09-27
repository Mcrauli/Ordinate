"""Upotettu 3D-tarkastusnäkymä: pistepilvi + malli samassa välilehdessä.

pyqtgraph.opengl (MIT) — upotettava QWidget. Hiiri kääntää katseen, WASD+QE
lentää (Shift = nopeampi). Pilvi ladataan taustasäikeessä ettei GUI jäädy.
Näkymämoodit: Väri / Residuaali (punainen = malli ei kata) / Vain puuttuvat.
"""
from __future__ import annotations

import codecs
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtWidgets
from ordinate.gui.safe import guard

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
import pyqtgraph.opengl as gl  # noqa: E402
from pyqtgraph import Vector  # noqa: E402

# 6 M pistetta jaadytti tarkastelun: lataus, taulukkojen rakennus ja
# residuaaliluokittelu kasvavat kaikki lineaarisesti. 1.5 M riittaa
# visuaaliseen tarkastukseen ja pitaa naytelman responsiivisena.
_MAX_VIEW_PTS = 1_500_000


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
        # FPS-tilassa kamera pysyy paikallaan ja katsepiste lasketaan uudelleen →
        # elevaation etumerkki on PÄINVASTAINEN kuin orbitissa (kasvava elevaatio
        # laskee katsepisteen). Siksi +dy (hiiri ylös = katso ylös, ei invertti).
        az = self.opts["azimuth"] - dx * 0.16
        el = float(np.clip(self.opts["elevation"] + dy * 0.16, -89.0, 89.0))
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

from ordinate.core.qa.residual import classify_explained  # noqa: E402,F401


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


# --- pilven lataus ALIPROSESSISSA ------------------------------------------
# E57-lukija ei vapauta GIL:ia (mitattu: yksi 834 MB tiedosto seisottaa toista
# saiketta 4.2 s), joten QThread ei auta — 36 tiedostoa jaadyttaa koko ikkunan
# viideksi minuutiksi. Sama ratkaisu kuin putkella: oma prosessi, stdout
# progressiksi.

class _CloudJob(QtCore.QObject):
    progress = QtCore.Signal(str)
    done = QtCore.Signal(object)   # dict: valmiiksi lasketut taulut + npz-polku
    failed = QtCore.Signal(str)

    def __init__(self, paths, max_pts: int, parent=None, model: dict | None = None,
                 reuse: Path | None = None) -> None:
        super().__init__(parent)
        self._paths = ([] if paths is None else
                       [str(p) for p in ([paths] if isinstance(paths, (str, Path)) else paths)])
        self._max = int(max_pts)
        self._model = model
        self._reuse = reuse
        self._model_file: Path | None = None
        self._proc: QtCore.QProcess | None = None
        self._npz: Path | None = None
        self._buf = ""
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._tail: list[str] = []

    def start(self) -> None:
        from ordinate.gui.process_worker import cli_command
        fd, tmp = tempfile.mkstemp(prefix="s2b_view_", suffix=".npz")
        os.close(fd)
        self._npz = Path(tmp)
        args = cli_command() + ["viewcloud", "--out", str(self._npz),
                                "--max-points", str(self._max)]
        if self._model is not None:
            fd, mtmp = tempfile.mkstemp(prefix="s2b_model_", suffix=".json")
            os.close(fd)
            self._model_file = Path(mtmp)
            self._model_file.write_text(json.dumps(self._model), encoding="utf-8")
            args += ["--model", str(self._model_file)]
        if self._reuse is not None:
            args += ["--reuse", str(self._reuse)]
        else:
            args += self._paths
        proc = QtCore.QProcess(self)
        proc.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        if sys.platform == "win32" and hasattr(proc, "setCreateProcessArgumentsModifier"):
            def _no_window(a):
                a.flags |= 0x08000000
            proc.setCreateProcessArgumentsModifier(_no_window)
        proc.readyReadStandardOutput.connect(self._on_out)
        proc.finished.connect(self._on_done)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        proc.start(args[0], args[1:])

    def cancel(self) -> None:
        if self._proc is not None:
            self._proc.kill()
        self._cleanup()

    def _on_out(self) -> None:
        if self._proc is None:
            return
        self._buf += self._dec.decode(bytes(self._proc.readAllStandardOutput())).replace("\r\n", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.strip()
            if line:
                self._tail.append(line)
                del self._tail[:-20]
                self.progress.emit(line)

    def _on_error(self, err) -> None:
        if err == QtCore.QProcess.ProcessError.FailedToStart:
            self._cleanup()
            self.failed.emit("pilvilukijaa ei voitu kaynnistaa")

    def _on_done(self, code: int, status) -> None:
        npz = self._npz
        proc_ok = code == 0 and status == QtCore.QProcess.ExitStatus.NormalExit
        self._cleanup(keep_file=True)
        if not proc_ok:
            if npz is not None:
                npz.unlink(missing_ok=True)
            self.failed.emit("\n".join(self._tail[-6:]) or f"virhekoodi {code}")
            return
        try:
            with np.load(npz) as z:
                data = {k: z[k] for k in z.files}
        except Exception as e:  # noqa: BLE001
            npz.unlink(missing_ok=True)
            self.failed.emit(str(e))
            return
        data["_npz"] = npz          # säilytetään: mallin muutos laskee residuaalin tästä
        self.done.emit(data)

    def _cleanup(self, keep_file: bool = False) -> None:
        if self._proc is not None:
            self._proc.deleteLater()
            self._proc = None
        if self._model_file is not None:
            self._model_file.unlink(missing_ok=True)
            self._model_file = None
        if not keep_file and self._npz is not None:
            self._npz.unlink(missing_ok=True)
            self._npz = None


class InspectView(QtWidgets.QWidget):
    """3D-välilehti: pilvi + malli. Hiiri kääntää, WASD+QE lentää."""

    _MODES = ["Väri", "Residuaali", "Vain puuttuvat"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model: dict | None = None
        self._cloud_path: str | None = None
        self._job = None
        self._res_job = None
        self._npz: Path | None = None
        self._pts_miss = None; self._res_miss = None
        # ladattu pilvi (välimuistissa → mallin muutos ei vaadi uudelleenlatausta)
        self._Ps = None; self._rgb = None; self._offset = None; self._pts = None
        self._rgba = None; self._res = None
        self._scatter = None; self._grid = None
        self._model_items: list = []
        # Pistekoko PIKSELEINÄ (pxMode=True): renderöityy luotettavasti joka
        # mittakaavassa. Maailmayksikkö (pxMode=False) rikkoi pienet huoneet —
        # lähellä koko ylitti GL:n max-pistekoon → mitään ei piirtynyt.
        self._psize = 6.0

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 8)
        self._load_btn = QtWidgets.QPushButton("Näytä pistepilvi")
        self._load_btn.clicked.connect(self._start_load)
        bar.addWidget(self._load_btn)
        self._cancel_btn = QtWidgets.QPushButton("Peruuta")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel)
        bar.addWidget(self._cancel_btn)
        bar.addWidget(QtWidgets.QLabel("Näkymä:"))
        self._mode = QtWidgets.QComboBox()
        self._mode.addItems(self._MODES)
        self._mode.setEnabled(False)
        self._mode.currentIndexChanged.connect(lambda _i: self._refresh_scatter())
        bar.addWidget(self._mode)
        bar.addWidget(QtWidgets.QLabel("Täyteys:"))
        self._size_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._size_slider.setMinimum(1); self._size_slider.setMaximum(16)
        self._size_slider.setValue(int(self._psize)); self._size_slider.setFixedWidth(110)
        self._size_slider.setEnabled(False)
        self._size_slider.valueChanged.connect(self._on_size)
        bar.addWidget(self._size_slider)
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
    @guard
    def set_source(self, model: dict, cloud_path) -> None:
        """Aseta tarkastettava malli + pilvipolku (yksi tai lista)."""
        self._model = model
        cloud_path = (list(cloud_path) if isinstance(cloud_path, (list, tuple))
                      else cloud_path)
        if cloud_path == self._cloud_path and self._Ps is not None:
            # Sama pilvi, eri malli: vanha residuaali on väärä (poistettu seinä
            # jättäisi pisteensä "selitetyiksi"), joten se lasketaan uudelleen.
            self._res = None; self._pts_miss = None; self._res_miss = None
            self._apply_model()
            return
        self._cloud_path = cloud_path
        self._stop_job(cancel=True)
        self._stop_res_job(cancel=True)
        self._drop_npz()
        self._Ps = None; self._pts = None
        self._res = None; self._pts_miss = None; self._res_miss = None
        self._view.clear()
        self._scatter = None; self._grid = None; self._model_items = []
        self._mode.setEnabled(False)
        self._load_btn.setEnabled(True)
        self._info.setText("Paina 'Näytä pistepilvi'.")

    # -- lataus --
    @guard
    def _start_load(self) -> None:
        if not self._model or not self._cloud_path or self._job is not None:
            return
        _first = (self._cloud_path[0] if isinstance(self._cloud_path, list)
                  else self._cloud_path)
        if not Path(_first).exists():
            self._info.setText("Pilvitiedostoa ei löydy — tarkastus vaatii alkuperäisen skannin.")
            return
        self._load_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        n = len(self._cloud_path) if isinstance(self._cloud_path, list) else 1
        self._info.setText(f"Ladataan pistepilveä ({n} skannia)…")
        self._job = _CloudJob(self._cloud_path, _MAX_VIEW_PTS, self, model=self._model)
        self._job.progress.connect(self._on_progress)
        self._job.done.connect(self._on_loaded)
        self._job.failed.connect(self._on_failed)
        self._job.start()

    def _stop_job(self, cancel: bool = False) -> None:
        job, self._job = self._job, None
        if job is None:
            return
        try:
            job.progress.disconnect()
            job.done.disconnect()
            job.failed.disconnect()
        except (RuntimeError, TypeError):
            pass
        if cancel:
            job.cancel()
        job.deleteLater()
        self._cancel_btn.setVisible(False)

    @guard
    def _on_cancel(self) -> None:
        self._stop_job(cancel=True)
        self._info.setText("Lataus peruttu.")
        self._load_btn.setEnabled(True)

    @guard
    def _on_progress(self, line: str) -> None:
        if not line.startswith("VALMIS"):
            self._info.setText(f"Ladataan pistepilveä… {line.strip()}")

    def _stop_res_job(self, cancel: bool = False) -> None:
        job, self._res_job = self._res_job, None
        if job is None:
            return
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for sig in (job.done, job.failed):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
        if cancel:
            job.cancel()
        job.deleteLater()

    def _drop_npz(self) -> None:
        if self._npz is not None:
            self._npz.unlink(missing_ok=True)
            self._npz = None

    @guard
    def _on_failed(self, msg: str) -> None:
        self._stop_job()
        self._info.setText(f"Lataus epäonnistui: {msg}")
        self._load_btn.setEnabled(True)

    @guard
    def _on_loaded(self, data) -> None:
        self._stop_job()
        self._load_btn.setEnabled(True)
        # EI numpy-työtä tässä prosessissa: taulut tulevat valmiina aliprosessista.
        self._drop_npz()
        self._npz = data.get("_npz")
        self._Ps = data["pts"]
        self._offset = data["offset"]
        self._pts = data["pts_c"]
        self._rgba = data["rgba"]
        self._take_residual(data)
        # perspektiivikoko (maailmayksikkö mm): lähellä pisteet suurenevat →
        # pinnat täyttyvät valokuvamaisiksi kun navigoi lähelle
        # pxMode=True (PIKSELIkoko): renderöityy luotettavasti joka mittakaavassa
        # ja frozen-exessä. pxMode=False (maailmakoko) näytti tyhjää pienissä
        # PLY-huoneissa releasessa.
        self._scatter = gl.GLScatterPlotItem(pos=self._pts, color=self._rgba, size=self._psize, pxMode=True)
        self._scatter.setGLOptions("opaque")
        self._view.addItem(self._scatter)
        # pohjaruudukko orientaatioon
        lo = self._pts.min(axis=0); hi = self._pts.max(axis=0)
        ext = float(max(hi[0] - lo[0], hi[1] - lo[1]))
        if not np.isfinite(ext) or ext <= 0:
            ext = 5000.0
        self._grid = gl.GLGridItem()
        self._grid.setSize(ext * 1.2, ext * 1.2)
        self._grid.setSpacing(1000, 1000)                 # 1 m ruudukko
        self._grid.translate((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        self._grid.setGLOptions("opaque")
        self._view.addItem(self._grid)
        span = float(np.linalg.norm(hi - lo))
        if not np.isfinite(span) or span <= 0:
            span = ext
        # Keskipiste JA katsekulma nollataan, ei vain etäisyyttä: lentotila
        # siirtää keskipistettä, ja edellisen pilven jäljiltä kamera katsoi
        # uuden rakennuksen ohi tyhjään (mitattu: 36 m sivussa, 80° ylöspäin).
        mid = (lo + hi) / 2.0
        self._view.setCameraPosition(pos=Vector(float(mid[0]), float(mid[1]), float(mid[2])),
                                     distance=max(span * 0.55, 500.0),
                                     elevation=30.0, azimuth=-45.0)
        self._mode.setEnabled(True)
        self._size_slider.setEnabled(True)
        self._apply_model()

    @guard
    def _on_size(self, val: int) -> None:
        self._psize = float(val)
        self._refresh_scatter()

    # -- mallin piirto + residuaali (välimuistin pisteillä, ei uudelleenlatausta) --
    @guard
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
        # Residuaali lasketaan aliprosessissa. Ensimmäisellä latauksella se
        # tuli jo pilven mukana; mallin muuttuessa (seinä poistettu) se lasketaan
        # uudelleen samoista pisteistä lukematta skanneja.
        if self._res is not None or self._npz is None or self._job is not None:
            self._refresh_scatter()
            return
        self._info.setText(f"{len(self._Ps)} pistettä · lasketaan residuaalia…")
        self._stop_res_job(cancel=True)
        self._res_job = _CloudJob(None, _MAX_VIEW_PTS, self, model=self._model,
                                  reuse=self._npz)
        self._res_job.done.connect(self._on_residual)
        self._res_job.failed.connect(
            lambda m: self._info.setText(f"Residuaalia ei voitu laskea: {m}"))
        self._res_job.start()

    @guard
    def _on_residual(self, data) -> None:
        self._stop_res_job()
        new_npz = data.get("_npz")
        if new_npz is not None and new_npz != self._npz:
            new_npz.unlink(missing_ok=True)
        self._take_residual(data)
        if self._mode.currentIndex() != 0:
            self._refresh_scatter()

    def _take_residual(self, data) -> None:
        if "res" not in data:
            self._res = None; self._pts_miss = None; self._res_miss = None
            return
        self._res = data["res"]
        self._pts_miss = data["pts_miss"]
        self._res_miss = data["res_miss"]
        self._info.setText(f"{len(self._pts)} pistettä · kattamatta {int(data['n_miss'])} "
                           "· syaani=seinä keltainen=pilari vihreä=palkki punainen=aukko")

    @guard
    def _refresh_scatter(self) -> None:
        if self._scatter is None or self._pts is None:
            return
        mode = self._mode.currentIndex()
        if self._res is None:
            mode = 0                                           # residuaali kesken
        s = self._psize
        if mode == 0:                                          # Väri
            self._scatter.setData(pos=self._pts, color=self._rgba, size=s, pxMode=True)
        elif mode == 1:                                        # Residuaali (kaikki)
            self._scatter.setData(pos=self._pts, color=self._res, size=s, pxMode=True)
        else:                                                  # Vain puuttuvat
            self._scatter.setData(pos=self._pts_miss, color=self._res_miss,
                                  size=s * 1.6, pxMode=True)

"""Pääikkuna."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim._version import __version__
from scan2bim.core.pipeline import PipelineConfig
from scan2bim.gui.file_panel import FilePanel
from scan2bim.gui.log_panel import LogPanel
from scan2bim.gui.plan_view import PlanView, _polygon_area
from scan2bim.gui.process_worker import ProcessWorker
from scan2bim.gui.stage_indicator import StageIndicator, stage_for_message
from scan2bim.gui.update_banner import UpdateBanner, UpdateChecker, perform_update
from scan2bim.gui.brand import app_icon, logo_pixmap
from scan2bim.gui.theme import TEXT
from scan2bim.core.updater import cleanup_old_exe


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"scan2bim  v{__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1100, 700)
        self.setMinimumSize(800, 500)

        self._worker = ProcessWorker(self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        # Layout
        central = QtWidgets.QWidget(self)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        # Otsikkorivi
        title_row = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        logo.setPixmap(logo_pixmap(28))
        logo.setFixedSize(28, 28)
        title_row.addWidget(logo)
        title_row.addSpacing(10)
        title = QtWidgets.QLabel("scan2bim")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()
        sub = QtWidgets.QLabel("Pistepilvi → arkkitehtimalli")
        sub.setObjectName("subtitle")
        title_row.addWidget(sub)
        root.addLayout(title_row)

        # Päivitysbanneri (näkyy vain kun uusi versio löytyy)
        self._update_banner = UpdateBanner()
        self._update_banner.update_requested.connect(
            lambda info: perform_update(info, self)
        )
        root.addWidget(self._update_banner)

        # Splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._file_panel = FilePanel()
        self._file_panel.convert_requested.connect(self._on_convert)
        # Scroll-alue: kun ikkuna madaltuu, paneeli vierii eikä puristu kasaan.
        panel_scroll = QtWidgets.QScrollArea()
        panel_scroll.setWidget(self._file_panel)
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        panel_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        panel_scroll.setFixedWidth(330)
        splitter.addWidget(panel_scroll)

        self._tabs = QtWidgets.QTabWidget()
        self._plan_view = PlanView()
        self._log_panel = LogPanel()
        self._tabs.addTab(self._plan_view, "Pohja")
        self._tabs.addTab(self._log_panel, "Loki")
        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, stretch=1)

        # Vaiheindikaattori + progressbar (näkyvät ajon aikana)
        self._stage = StageIndicator()
        self._stage.setVisible(False)
        root.addWidget(self._stage)

        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(6)
        root.addWidget(self._progress_bar)

        # Tulosfooter (näkyy konversion jälkeen): yhteenveto + avaa-painikkeet
        self._results_bar = self._build_results_bar()
        self._results_bar.setVisible(False)
        root.addWidget(self._results_bar)

        self._last_out: Path | None = None

        self.setCentralWidget(central)
        self.statusBar().showMessage("Valmis")

        self._log_panel.info(f"scan2bim {__version__} käynnistetty.")
        self._log_panel.info("Raahaa pistepilvi ikkunaan tai klikkaa drop-aluetta.")

        # Siivoa edellisen päivityksen .old-exe ja tarkista uusi versio.
        cleanup_old_exe()
        self._update_checker = UpdateChecker(self)
        self._update_checker.result.connect(self._on_update_check)
        self._update_checker.start()

    def _on_update_check(self, info: object) -> None:
        if info is not None:
            self._update_banner.show_for(info)

    def _build_results_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("panel")
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)
        check = QtWidgets.QLabel("✓")
        check.setStyleSheet("color:#22c55e;font-size:18px;font-weight:800;")
        row.addWidget(check)
        self._results_label = QtWidgets.QLabel("")
        self._results_label.setStyleSheet(f"color:{TEXT};font-size:13px;")
        row.addWidget(self._results_label)
        row.addStretch()
        self._open_ifc_btn = QtWidgets.QPushButton("Avaa IFC")
        self._open_ifc_btn.clicked.connect(self._open_ifc)
        row.addWidget(self._open_ifc_btn)
        open_dir = QtWidgets.QPushButton("Avaa kansio")
        open_dir.setObjectName("linkbtn")
        open_dir.clicked.connect(self._open_folder)
        row.addWidget(open_dir)
        return bar

    def _on_convert(self, inputs: list, out: Path, cfg: PipelineConfig) -> None:
        self._log_panel.clear()
        self._last_out = out
        self._results_bar.setVisible(False)
        self._stage.reset()
        self._stage.setVisible(True)
        self._stage.set_active(0)
        label = inputs[0].name if len(inputs) == 1 else f"{len(inputs)} skannia"
        self._log_panel.info(f"Aloitetaan: {label}")
        self._file_panel.set_busy(True)
        self._progress_bar.setVisible(True)
        self.statusBar().showMessage("Käsitellään…")
        self._worker.start_job(inputs, out, cfg)

    def _on_progress(self, msg: str) -> None:
        self._log_panel.info(msg)
        self.statusBar().showMessage(msg)
        st = stage_for_message(msg)
        if st is not None:
            self._stage.set_active(st)

    def _on_finished(self, result: object) -> None:
        self._file_panel.set_busy(False)
        self._progress_bar.setVisible(False)
        self._stage.set_done()
        self._log_panel.success("✓ Valmis!")
        models = result if isinstance(result, list) else [result]
        if isinstance(result, list):
            lines = [f"{len(result)} kerrosta käsitelty:"]
            lines += [f"  kerros {i}: {m.summary()}" for i, m in enumerate(result)]
            self._log_panel.set_results("\n".join(lines))
            self._plan_view.show_models(result)
        else:
            self._log_panel.set_results(result.summary())
            self._plan_view.show_model(result)
        self._tabs.setCurrentWidget(self._plan_view)   # näytä pohja heti
        self._show_results(models)
        self.statusBar().showMessage("Valmis")

    def _show_results(self, models: list) -> None:
        walls = sum(len(getattr(m, "walls", []) or []) for m in models)
        spaces = [s for m in models for s in (getattr(m, "spaces", []) or [])]
        area = sum(_polygon_area(s.boundary) for s in spaces) / 1e6  # m²
        ops = [o for m in models for o in (getattr(m, "openings", []) or [])]
        doors = sum(1 for o in ops if o.opening_type == "door")
        wins = len(ops) - doors
        parts = [f"<b>{walls}</b> seinää", f"<b>{len(spaces)}</b> huonetta ({area:.0f} m²)",
                 f"<b>{doors}</b> ovea", f"<b>{wins}</b> ikkunaa"]
        if len(models) > 1:
            parts.insert(0, f"<b>{len(models)}</b> kerrosta")
        self._results_label.setText("&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts))
        self._open_ifc_btn.setEnabled(self._find_ifc() is not None)
        self._results_bar.setVisible(True)

    def _find_ifc(self) -> Path | None:
        if self._last_out is None or not self._last_out.exists():
            return None
        for name in ("building.ifc", "model.ifc"):
            p = self._last_out / name
            if p.exists():
                return p
        hits = sorted(self._last_out.glob("**/*.ifc"))
        return hits[0] if hits else None

    def _open_ifc(self) -> None:
        p = self._find_ifc()
        if p is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(p)))

    def _open_folder(self) -> None:
        if self._last_out is not None and self._last_out.exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._last_out)))

    def _on_failed(self, error: str) -> None:
        self._file_panel.set_busy(False)
        self._progress_bar.setVisible(False)
        self._stage.setVisible(False)
        self._log_panel.error(f"Virhe: {error}")
        self.statusBar().showMessage("Virhe")
        QtWidgets.QMessageBox.critical(self, "Virhe", error)

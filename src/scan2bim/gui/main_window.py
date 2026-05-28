"""Pääikkuna."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from scan2bim._version import __version__
from scan2bim.core.pipeline import PipelineConfig
from scan2bim.gui.file_panel import FilePanel
from scan2bim.gui.log_panel import LogPanel
from scan2bim.gui.process_worker import ProcessWorker


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"scan2bim  v{__version__}")
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
        title = QtWidgets.QLabel("scan2bim")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch()
        sub = QtWidgets.QLabel("Pistepilvi → arkkitehtimalli")
        sub.setObjectName("subtitle")
        title_row.addWidget(sub)
        root.addLayout(title_row)

        # Splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._file_panel = FilePanel()
        self._file_panel.convert_requested.connect(self._on_convert)
        self._file_panel.setFixedWidth(320)
        splitter.addWidget(self._file_panel)

        self._log_panel = LogPanel()
        splitter.addWidget(self._log_panel)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, stretch=1)

        # Progressbar
        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedHeight(6)
        root.addWidget(self._progress_bar)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Valmis")

        self._log_panel.info(f"scan2bim {__version__} käynnistetty.")
        self._log_panel.info("Raahaa pistepilvi ikkunaan tai klikkaa drop-aluetta.")

    def _on_convert(self, inp: Path, out: Path, cfg: PipelineConfig) -> None:
        self._log_panel.clear()
        self._log_panel.info(f"Aloitetaan: {inp.name}")
        self._file_panel.set_busy(True)
        self._progress_bar.setVisible(True)
        self.statusBar().showMessage("Käsitellään…")
        self._worker.start_job(inp, out, cfg)

    def _on_progress(self, msg: str) -> None:
        self._log_panel.info(msg)
        self.statusBar().showMessage(msg)

    def _on_finished(self, model: object) -> None:
        self._file_panel.set_busy(False)
        self._progress_bar.setVisible(False)
        self._log_panel.success("✓ Valmis!")
        self._log_panel.set_results(model.summary())
        self.statusBar().showMessage("Valmis")

    def _on_failed(self, error: str) -> None:
        self._file_panel.set_busy(False)
        self._progress_bar.setVisible(False)
        self._log_panel.error(f"Virhe: {error}")
        self.statusBar().showMessage("Virhe")
        QtWidgets.QMessageBox.critical(self, "Virhe", error)

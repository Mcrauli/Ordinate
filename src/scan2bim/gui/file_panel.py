"""Vasen paneeli: syötetiedosto, asetukset, Convert-painike."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim.core.pipeline import PipelineConfig
from scan2bim.gui.theme import ACCENT, BG_WIDGET, TEXT_DIM


class DropZone(QtWidgets.QLabel):
    """Raahaa tiedosto tähän -alue."""
    file_dropped = QtCore.Signal(Path)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(100)
        self._set_empty()
        self.setStyleSheet(
            f"border: 2px dashed #475569; border-radius: 8px;"
            f"color: {TEXT_DIM}; background: {BG_WIDGET};"
        )

    def _set_empty(self) -> None:
        self.setText("Raahaa pistepilvi tähän\n(E57 · LAS/LAZ · PTS)")

    def set_file(self, path: Path) -> None:
        self.setText(f"📁  {path.name}")
        self.setStyleSheet(
            f"border: 2px solid {ACCENT}; border-radius: 8px;"
            f"color: #f1f5f9; background: {BG_WIDGET};"
        )

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            p = Path(urls[0].toLocalFile())
            if p.suffix.lower() in {".e57", ".las", ".laz", ".pts", ".ply"}:
                self.set_file(p)
                self.file_dropped.emit(p)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Avaa pistepilvi",
            "",
            "Point cloud (*.e57 *.las *.laz *.pts *.ply)",
        )
        if path:
            p = Path(path)
            self.set_file(p)
            self.file_dropped.emit(p)


class FilePanel(QtWidgets.QWidget):
    """Vasen ohjauspaneeli."""
    convert_requested = QtCore.Signal(Path, Path, PipelineConfig)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._input_path: Path | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Syötetiedosto
        in_label = QtWidgets.QLabel("Pistepilvi")
        in_label.setObjectName("section")
        layout.addWidget(in_label)

        self._drop = DropZone()
        self._drop.file_dropped.connect(self._on_file)
        layout.addWidget(self._drop)

        # Kansio
        out_label = QtWidgets.QLabel("Tuloskansio")
        out_label.setObjectName("section")
        layout.addWidget(out_label)

        out_row = QtWidgets.QHBoxLayout()
        self._out_edit = QtWidgets.QLineEdit("output")
        out_row.addWidget(self._out_edit, stretch=1)
        browse = QtWidgets.QPushButton("…")
        browse.setFixedWidth(36)
        browse.clicked.connect(self._browse_out)
        out_row.addWidget(browse)
        layout.addLayout(out_row)

        # Asetukset
        cfg_label = QtWidgets.QLabel("Asetukset")
        cfg_label.setObjectName("section")
        layout.addWidget(cfg_label)

        form = QtWidgets.QFormLayout()
        form.setSpacing(8)

        self._detector = QtWidgets.QComboBox()
        self._detector.addItems(["ransac", "density"])
        form.addRow("Detektori:", self._detector)

        self._voxel = QtWidgets.QDoubleSpinBox()
        self._voxel.setRange(5, 100)
        self._voxel.setValue(20)
        self._voxel.setSuffix(" mm")
        form.addRow("Voxel-koko:", self._voxel)

        self._ifc = QtWidgets.QCheckBox("IFC")
        self._ifc.setChecked(True)
        self._dxf = QtWidgets.QCheckBox("DXF")
        self._dxf.setChecked(True)
        ex_row = QtWidgets.QHBoxLayout()
        ex_row.addWidget(self._ifc)
        ex_row.addWidget(self._dxf)
        ex_row.addStretch()
        form.addRow("Export:", ex_row)

        layout.addLayout(form)

        layout.addStretch()

        # Convert
        self._btn = QtWidgets.QPushButton("Konvertoi")
        self._btn.setEnabled(False)
        self._btn.clicked.connect(self._on_convert)
        layout.addWidget(self._btn)

    def _on_file(self, path: Path) -> None:
        self._input_path = path
        self._btn.setEnabled(True)
        # Ehdota tuloskansio syötteen viereen
        self._out_edit.setText(str(path.parent / "output"))

    def _browse_out(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Tuloskansio")
        if d:
            self._out_edit.setText(d)

    def _on_convert(self) -> None:
        if not self._input_path:
            return
        cfg = PipelineConfig(
            voxel_size=self._voxel.value(),
            detector=self._detector.currentText(),
            export_ifc=self._ifc.isChecked(),
            export_dxf=self._dxf.isChecked(),
        )
        self.convert_requested.emit(
            self._input_path,
            Path(self._out_edit.text()),
            cfg,
        )

    def set_busy(self, busy: bool) -> None:
        self._btn.setEnabled(not busy)
        self._btn.setText("Käsitellään…" if busy else "Konvertoi")

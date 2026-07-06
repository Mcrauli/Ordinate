"""Vasen paneeli: syötetiedosto, asetukset, Convert-painike."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from scan2bim.core.pipeline import PipelineConfig
from scan2bim.core.segmentation.pointnet_filter import _find_model_path
from scan2bim.gui.theme import ACCENT, BG_WIDGET, TEXT_DIM

_MODEL_AVAILABLE = _find_model_path() is not None


_EXTS = {".e57", ".las", ".laz", ".pts", ".ply"}


def _collect_scan_files(paths: list[Path]) -> list[Path]:
    """Kerää skannaukset: tiedostot suoraan tai kaikki tiedostot kansiosta."""
    result: list[Path] = []
    for p in paths:
        if p.is_dir():
            for ext in _EXTS:
                result.extend(sorted(p.glob(f"*{ext}")))
        elif p.suffix.lower() in _EXTS:
            result.append(p)
    return result


class DropZone(QtWidgets.QLabel):
    """Raahaa tiedosto(t) tähän -alue. Tukee montaa skannia (monikerros)."""
    files_dropped = QtCore.Signal(list)   # list[Path]

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
        self.setText("Raahaa pistepilviä tai kansio tähän\n(E57 · LAS/LAZ · PTS · PLY)")

    def set_files(self, paths: list[Path]) -> None:
        if len(paths) == 1:
            self.setText(f"📁  {paths[0].name}")
        else:
            self.setText(f"📁  {len(paths)} skannia (monikerros)")
        self.setStyleSheet(
            f"border: 2px solid {ACCENT}; border-radius: 8px;"
            f"color: #f1f5f9; background: {BG_WIDGET};"
        )

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        raw = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
        paths = _collect_scan_files(raw)
        if paths:
            self.set_files(paths)
            self.files_dropped.emit(paths)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Avaa pistepilvi(t)",
            "",
            "Point cloud (*.e57 *.las *.laz *.pts *.ply)",
        )
        if files:
            paths = [Path(f) for f in files]
            self.set_files(paths)
            self.files_dropped.emit(paths)


class FilePanel(QtWidgets.QWidget):
    """Vasen ohjauspaneeli."""
    convert_requested = QtCore.Signal(object, Path, PipelineConfig)   # list[Path], out, cfg

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._input_paths: list[Path] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Syötetiedosto
        in_label = QtWidgets.QLabel("Pistepilvi")
        in_label.setObjectName("section")
        layout.addWidget(in_label)

        self._drop = DropZone()
        self._drop.files_dropped.connect(self._on_files)
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

        self._voxel = QtWidgets.QDoubleSpinBox()
        self._voxel.setRange(0.5, 50.0)
        self._voxel.setSingleStep(0.5)
        self._voxel.setValue(12.0)
        self._voxel.setSuffix(" mm")

        self._auto_voxel = QtWidgets.QCheckBox("Automaattinen (suositeltu)")
        self._auto_voxel.setChecked(True)
        self._auto_voxel.toggled.connect(lambda on: self._voxel.setEnabled(not on))
        self._voxel.setEnabled(False)
        vx_row = QtWidgets.QVBoxLayout()
        vx_row.setSpacing(4)
        vx_row.addWidget(self._auto_voxel)
        vx_row.addWidget(self._voxel)
        form.addRow("Voxel-koko:", vx_row)

        self._icp = QtWidgets.QCheckBox("ICP-hienorekisteröinti")
        self._icp.setChecked(False)
        self._icp.setToolTip(
            "Vain kohdistamattomille raakaskanneille (erilliset E57:t eri poseista).\n"
            "Jos pistepilvi on jo yhdistetty keilainohjelmassa (esim. yksi PLY tai "
            "valmiiksi rekisteröidyt skannit), JÄTÄ POIS — se vain tuplaa ajan "
            "parantamatta tulosta."
        )
        form.addRow("Rekisteröinti:", self._icp)

        self._qa = QtWidgets.QCheckBox("QA/LOA-raportti")
        self._qa.setChecked(True)
        self._qa_tol = QtWidgets.QDoubleSpinBox()
        self._qa_tol.setRange(0.5, 25.0)
        self._qa_tol.setSingleStep(0.5)
        self._qa_tol.setValue(2.5)
        self._qa_tol.setSuffix(" mm")
        qa_row = QtWidgets.QHBoxLayout()
        qa_row.addWidget(self._qa)
        qa_row.addWidget(QtWidgets.QLabel("tol:"))
        qa_row.addWidget(self._qa_tol)
        qa_row.addStretch()
        form.addRow("Tarkkuus:", qa_row)

        self._sem_filter = QtWidgets.QCheckBox("Kalustesuodatus (PointNet)")
        self._sem_filter.setChecked(_MODEL_AVAILABLE)
        if _MODEL_AVAILABLE:
            self._sem_filter.setToolTip(
                "S3DIS PointNet ONNX: poistaa kalusteet ja krääsän ennen detektiota.\n"
                "Parantaa tarkkuutta kalustetuissa tiloissa."
            )
        else:
            self._sem_filter.setToolTip(
                "Malli puuttuu (models/s3dis_pointnet.onnx).\n"
                "Aja: python scripts/export_s3dis_model.py\n"
                "Kun malli on valmis, tämä kytkin aktivoituu automaattisesti."
            )
            self._sem_filter.setEnabled(False)
        form.addRow("Kalustesuodatus:", self._sem_filter)

        self._site_type = QtWidgets.QComboBox()
        self._site_type.addItems(["Asunto / toimisto", "Liiketila / työmaa"])
        self._site_type.setToolTip(
            "Liiketila / työmaa: suodatinmalli joka poistaa lattiasta kattoon\n"
            "ulottuvat hyllyrivit ja työmaakrääsän (myymälät, varastot, runko-\n"
            "vaiheen kohteet). Asunnoissa ja toimistoissa oletus on tarkempi."
        )
        self._site_type.setEnabled(_MODEL_AVAILABLE)
        form.addRow("Kohdetyyppi:", self._site_type)

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

    def _on_files(self, paths: list[Path]) -> None:
        self._input_paths = paths
        self._btn.setEnabled(bool(paths))
        if paths:
            # Ehdota tuloskansio ensimmäisen syötteen viereen
            self._out_edit.setText(str(paths[0].parent / "output"))

    def _browse_out(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Tuloskansio")
        if d:
            self._out_edit.setText(d)

    def _on_convert(self) -> None:
        if not self._input_paths:
            return
        cfg = PipelineConfig(
            voxel_size=self._voxel.value(),
            auto_voxel=self._auto_voxel.isChecked(),
            detector="contour",
            export_ifc=self._ifc.isChecked(),
            export_dxf=self._dxf.isChecked(),
            export_qa=self._qa.isChecked(),
            qa_tolerance=self._qa_tol.value(),
            icp_refine=self._icp.isChecked(),
            semantic_filter_mode=(
                ("pointnet-retail" if self._site_type.currentIndex() == 1 else "pointnet")
                if self._sem_filter.isChecked() else "off"
            ),
        )
        self.convert_requested.emit(
            self._input_paths,
            Path(self._out_edit.text()),
            cfg,
        )

    def set_busy(self, busy: bool) -> None:
        self._btn.setEnabled(not busy)
        self._btn.setText("Käsitellään…" if busy else "Konvertoi")

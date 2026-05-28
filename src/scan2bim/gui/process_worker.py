"""QThread joka ajaa Pipeline.run() taustalla ja emittoi progress-signaaleja."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from scan2bim.core.pipeline import Pipeline, PipelineConfig
from scan2bim.schemas.model import StructuralModel


class ProcessWorker(QtCore.QThread):
    progress = QtCore.Signal(str)
    finished = QtCore.Signal(object)   # StructuralModel
    failed = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._input: Path | None = None
        self._output: Path | None = None
        self._config: PipelineConfig = PipelineConfig()

    def start_job(
        self,
        input_path: Path,
        output_dir: Path,
        config: PipelineConfig,
    ) -> None:
        self._input = input_path
        self._output = output_dir
        self._config = config
        self.start()

    def run(self) -> None:
        try:
            pipeline = Pipeline(self._config, progress=self.progress.emit)
            model = pipeline.run(self._input, self._output)
            self.finished.emit(model)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

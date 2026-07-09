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
        self._inputs: list[Path] = []
        self._output: Path | None = None
        self._config: PipelineConfig = PipelineConfig()

    def start_job(
        self,
        inputs: list[Path],
        output_dir: Path,
        config: PipelineConfig,
    ) -> None:
        self._inputs = list(inputs)
        self._output = output_dir
        self._config = config
        self.start()

    def run(self) -> None:
        try:
            pipeline = Pipeline(self._config, progress=self.progress.emit)
            # AINA run_floors — myös yhdelle tiedostolle. Se on tuotantopolku
            # (lohkoluku isoille skanneille, kerrosjako, diagnostiikka). Vanha
            # yhden-tiedoston run() lataa koko pilven kerralla (iso E57/PLY →
            # muisti loppuu tai kaatuu) eikä sitä pidä käyttää GUI:sta.
            # run_floors palauttaa listan (malli per kerros). _on_finished
            # käsittelee listan (show_models) → monikerros näkyy oikein.
            models = pipeline.run_floors(self._inputs, self._output)
            self.finished.emit(models)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

"""Ajaa putken ERILLISENÄ PROSESSINA ja emittoi progress-signaaleja.

Aiempi versio ajoi Pipeline.run():n QThreadissa samassa prosessissa. Putken
semantiikkaketju on täynnä puhdasta Python-silmukkaa, joka pitää GIL:iä →
Qt:n tapahtumasilmukka ei päässyt ajoon ja käyttöliittymä jäätyi kesken ajon.
Erillinen prosessi ei voi jäädyttää sitä: GUI vain lukee stdoutia.
"""
from __future__ import annotations

import codecs
import dataclasses
import json
import sys
from pathlib import Path

from PySide6 import QtCore

from scan2bim.core.pipeline import PipelineConfig
from scan2bim.schemas.model import StructuralModel

_CREATE_NO_WINDOW = 0x08000000


def cli_command() -> list[str]:
    """Komento joka ajaa saman koodin komentoriviltä.

    Pakatussa buildissa se on `scan2bim-cli.exe` GUI-exen vieressä (sama
    Analysis, sama malli). Kehityksessä nykyinen tulkki.
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).with_name("scan2bim-cli.exe")
        if exe.exists():
            return [str(exe)]
        return [str(Path(sys.executable).with_name("scan2bim-cli"))]
    return [sys.executable, "-m", "scan2bim.cli"]


class ProcessWorker(QtCore.QObject):
    progress = QtCore.Signal(str)
    finished = QtCore.Signal(object)   # list[StructuralModel]
    failed = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QtCore.QProcess | None = None
        self._output: Path | None = None
        self._cfg_file: Path | None = None
        self._buf = ""
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._tail: list[str] = []

    # -- julkinen API (sama kuin ennen) --
    def start_job(self, inputs: list[Path], output_dir: Path, config: PipelineConfig) -> None:
        if self._proc is not None:
            self.failed.emit("ajo on jo käynnissä")
            return
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output = output_dir
        self._buf = ""
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._tail = []

        raw = {k: (str(v) if isinstance(v, Path) else v)
               for k, v in dataclasses.asdict(config).items()}
        self._cfg_file = output_dir / "_run_config.json"
        self._cfg_file.write_text(json.dumps(raw), encoding="utf-8")

        args = cli_command()
        args += ["run", "--out", str(output_dir), "--config", str(self._cfg_file)]
        args += [str(p) for p in inputs]

        proc = QtCore.QProcess(self)
        proc.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        if sys.platform == "win32" and hasattr(proc, "setCreateProcessArgumentsModifier"):
            def _no_window(a):
                a.flags |= _CREATE_NO_WINDOW
            proc.setCreateProcessArgumentsModifier(_no_window)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(self._on_output)
        proc.finished.connect(self._on_done)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        proc.start(args[0], args[1:])

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.kill()

    def isRunning(self) -> bool:
        return self._proc is not None

    # -- sisäinen --
    def _on_output(self) -> None:
        if self._proc is None:
            return
        # Inkrementaalinen dekooderi: monitavuinen merkki voi katketa kahden
        # luvun valiin, jolloin per-lohko decode() tuottaa korvausmerkin.
        data = self._dec.decode(bytes(self._proc.readAllStandardOutput()))
        self._buf += data.replace("\r\n", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if not line:
                continue
            self._tail.append(line)
            del self._tail[:-40]
            self.progress.emit(line)

    def _on_error(self, err) -> None:
        if err == QtCore.QProcess.ProcessError.FailedToStart:
            self._cleanup()
            self.failed.emit("komentorivikomponenttia ei voitu käynnistää")

    def _on_done(self, code: int, status) -> None:
        if self._buf.strip():
            self.progress.emit(self._buf.strip())
            self._buf = ""
        self._cleanup()
        if status == QtCore.QProcess.ExitStatus.CrashExit:
            self.failed.emit("ajo keskeytyi (prosessi kaatui)\n" + "\n".join(self._tail[-12:]))
            return
        if code != 0:
            self.failed.emit(f"ajo päättyi virhekoodiin {code}\n" + "\n".join(self._tail[-12:]))
            return
        try:
            models = self._load_models()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"tuloksia ei voitu lukea: {exc}")
            return
        if not models:
            self.failed.emit("ajo valmistui mutta mallia ei löytynyt")
            return
        self.finished.emit(models)

    def _load_models(self) -> list[StructuralModel]:
        out = self._output
        if out is None:
            return []
        paths = sorted(out.glob("floor_*/model.json"))
        if not paths and (out / "model.json").exists():
            paths = [out / "model.json"]
        return [StructuralModel.load(p) for p in paths]

    def _cleanup(self) -> None:
        if self._cfg_file is not None:
            try:
                self._cfg_file.unlink()
            except OSError:
                pass
            self._cfg_file = None
        if self._proc is not None:
            self._proc.deleteLater()
            self._proc = None

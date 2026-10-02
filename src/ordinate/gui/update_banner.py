"""Non-modal banner shown at the top of the main window when a newer
Ordinate release is available on GitHub.

Wired by :class:`MainWindow` to:
    1. A background ``UpdateChecker`` that polls
       :func:`ordinate.core.updater.check_for_update` once on startup.
    2. A click handler that verifies the release signature, downloads the
       package with progress, checks it against the signed manifest and
       hands it to :func:`apply_downloaded_update` before quitting the app.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ordinate.core.updater import (
    DEFAULT_REPO,
    UpdateInfo,
    apply_downloaded_update,
    check_for_update,
    download_asset,
    fetch_signed_manifest,
    is_running_bundled,
)
from ordinate.core.release_signing import VerificationError


class UpdateChecker(QtCore.QObject):
    """Runs :func:`check_for_update` on a worker thread, emits result.

    Silent on failure: no-update and check-error are both ``None``.
    """

    result = QtCore.Signal(object)  # UpdateInfo | None

    def start(self, *, repo: str = DEFAULT_REPO) -> None:
        QtCore.QThreadPool.globalInstance().start(_CheckRunnable(self, repo=repo))


class _CheckRunnable(QtCore.QRunnable):
    def __init__(self, owner: UpdateChecker, *, repo: str) -> None:
        super().__init__()
        self._owner = owner
        self._repo = repo

    def run(self) -> None:  # type: ignore[override]
        try:
            info = check_for_update(repo=self._repo)
        except Exception:
            info = None
        self._owner.result.emit(info)


class UpdateBanner(QtWidgets.QFrame):
    """Call-to-action strip that appears when an update is found."""

    update_requested = QtCore.Signal(object)  # UpdateInfo

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("update_banner")
        self.setProperty("role", "update_banner")
        self.setStyleSheet(
            "#update_banner{background:#2a3d12;border:1px solid #c6f24e;"
            "border-radius:8px;} QLabel{color:#e9f6c9;}"
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        self._label = QtWidgets.QLabel("")
        self._label.setWordWrap(True)
        layout.addWidget(self._label, stretch=1)

        self._button = QtWidgets.QPushButton("Päivitä nyt")
        self._button.clicked.connect(self._on_clicked)
        layout.addWidget(self._button)

        self._dismiss = QtWidgets.QPushButton("Myöhemmin")
        self._dismiss.clicked.connect(self.hide)
        layout.addWidget(self._dismiss)

        self._info: UpdateInfo | None = None
        self.hide()

    def show_for(self, info: UpdateInfo) -> None:
        self._info = info
        size_mb = info.download_size / (1024 * 1024) if info.download_size else 0
        size_str = f" ({size_mb:.0f} MB)" if size_mb else ""
        self._label.setText(
            f"Uusi versio <b>{info.tag}</b> saatavilla{size_str}. "
            f"Klikkaa 'Päivitä nyt' niin lataus ja vaihto hoituu automaattisesti."
        )
        self.show()

    def _on_clicked(self) -> None:
        if self._info is not None:
            self.update_requested.emit(self._info)


class UpdateProgressDialog(QtWidgets.QProgressDialog):
    finished_ok = QtCore.Signal(Path)
    failed = QtCore.Signal(str)

    def __init__(self, info: UpdateInfo, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(f"Ladataan {info.tag}…", "Peruuta", 0, 100, parent)
        self.setWindowTitle("Ordinate — päivitys")
        self.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self._info = info
        self._cancelled = False
        self.canceled.connect(self._on_cancel)

    def _on_cancel(self) -> None:
        self._cancelled = True

    def start(self, target_path: Path) -> None:
        QtCore.QThreadPool.globalInstance().start(
            _DownloadRunnable(self, target_path=target_path)
        )

    def report_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        percent = int(downloaded * 100 / total)
        QtCore.QMetaObject.invokeMethod(
            self,
            "setValue",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(int, percent),
        )

    def is_cancelled(self) -> bool:
        return self._cancelled


class _DownloadRunnable(QtCore.QRunnable):
    def __init__(self, owner: UpdateProgressDialog, *, target_path: Path) -> None:
        super().__init__()
        self._owner = owner
        self._target_path = target_path

    def run(self) -> None:  # type: ignore[override]
        info = self._owner._info  # noqa: SLF001

        def progress_cb(downloaded: int, total: int) -> None:
            if self._owner.is_cancelled():
                raise RuntimeError("cancelled")
            self._owner.report_progress(downloaded, total)

        try:
            manifest = fetch_signed_manifest(info.download_url, info.version)
        except VerificationError as exc:
            self._owner.failed.emit(
                f"Päivityksen allekirjoitusta ei voitu varmistaa ({exc}). "
                "Päivitystä ei asennettu.")
            return
        try:
            download_asset(
                info.download_url,
                self._target_path,
                progress_cb=progress_cb,
                expected_sha256=manifest["sha256"],
                expected_size=manifest["size"],
            )
        except RuntimeError:
            return
        except Exception as exc:
            self._owner.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self._owner.finished_ok.emit(self._target_path)


def perform_update(info: UpdateInfo, parent: QtWidgets.QWidget | None = None) -> None:
    """Download + swap. Quits the running app on success."""
    if not is_running_bundled():
        QtWidgets.QMessageBox.information(
            parent,
            "Päivitys",
            "Itsepäivitys on käytettävissä vain asennetulle .exe-versiolle. "
            "Lataa uusin versio manuaalisesti:\n" + info.release_url,
        )
        return

    target = Path(tempfile.gettempdir()) / Path(info.download_url).name
    dialog = UpdateProgressDialog(info, parent)

    def on_ok(downloaded_path: Path) -> None:
        dialog.setLabelText("Asennetaan päivitys…")
        dialog.setCancelButton(None)
        dialog.setRange(0, 0)
        QtWidgets.QApplication.processEvents()

        # apply_downloaded_update valitsee oikean tavan. One-dir-ZIP: vaihto tehdään
        # APUPROSESSILLA joka odottaa tämän appin sulkeutumista (base_library.zip on
        # lukossa ajon aikana → in-place-vaihto kaatuisi WinError 32:een) → palauttaa
        # True ja app pitää sulkea, apuri asentaa + avaa uudelleen. Legacy one-file:
        # replace_exe on jo tehnyt vaihdon → False, käyttäjä avaa uudelleen itse.
        try:
            via_helper = apply_downloaded_update(downloaded_path, info.download_url)
        except Exception as exc:
            dialog.close()
            QtWidgets.QMessageBox.critical(
                parent,
                "Päivitys epäonnistui",
                f"Vaihto ei onnistunut: {type(exc).__name__}: {exc}\n"
                f"Lataa manuaalisesti: {info.release_url}",
            )
            return
        dialog.close()
        if via_helper:
            QtWidgets.QMessageBox.information(
                parent,
                "Päivitys valmis asennettavaksi",
                f"Ordinate {info.tag} asennetaan kun sovellus suljetaan, ja se "
                f"avautuu automaattisesti uudelleen.\n\nPaina OK sulkeaksesi nyt.",
            )
        else:
            QtWidgets.QMessageBox.information(
                parent,
                "Päivitys asennettu",
                f"Ordinate {info.tag} on nyt asennettu.\n\n"
                f"Avaa Ordinate uudelleen työpöydältä tai Käynnistä-valikosta.",
            )
        os._exit(0)

    def on_fail(message: str) -> None:
        dialog.close()
        QtWidgets.QMessageBox.critical(
            parent,
            "Päivitys epäonnistui",
            f"Lataus ei onnistunut: {message}\n"
            f"Lataa manuaalisesti: {info.release_url}",
        )

    dialog.finished_ok.connect(on_ok)
    dialog.failed.connect(on_fail)
    dialog.start(target)
    dialog.exec()

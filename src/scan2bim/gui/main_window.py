"""Pääikkuna."""
from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from scan2bim.gui.safe import guard
from scan2bim.gui.run_timing import clock, fmt_duration, slowest_steps

from scan2bim._version import __version__
from scan2bim.core.pipeline import PipelineConfig
from scan2bim.core.qa.project_learning import CorrectionLearner
from scan2bim.gui.file_panel import FilePanel
from scan2bim.gui.log_panel import LogPanel
from scan2bim.gui.plan_view import PlanView, _polygon_area
from scan2bim.gui.process_worker import ProcessWorker
from scan2bim.gui.review_panel import ReviewPanel
from scan2bim.gui.inspect_view import InspectView
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

        # Sivupalkki: asetukset vierivät, Konvertoi kiinnitetty alalaitaan
        # (FilePanel hoitaa oman vieritys/footer-rakenteensa).
        self._file_panel = FilePanel()
        self._file_panel.setObjectName("sidebar")
        self._file_panel.setFixedWidth(336)
        self._file_panel.convert_requested.connect(self._on_convert)
        splitter.addWidget(self._file_panel)

        self._tabs = QtWidgets.QTabWidget()
        self._plan_view = PlanView()
        self._plan_view.element_picked.connect(self._on_plan_pick)
        self._plan_view.elements_boxed.connect(self._on_plan_box)
        self._review = ReviewPanel()
        self._review.element_selected.connect(self._on_review_select)
        self._review.delete_requested.connect(self._on_review_delete)
        self._review.accept_requested.connect(self._on_review_accept)
        self._review.setMinimumWidth(300)
        self._log_panel = LogPanel()
        self._inspect_view = InspectView()
        # Tarkistus pohjan VIERESSÄ eikä omana välilehtenä: jokainen listan
        # valinta korostaa seinän pohjassa, ja välilehtien välillä pomppiminen
        # teki kymmenien seinien läpikäynnistä käytännössä mahdotonta.
        self._plan_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._plan_split.setChildrenCollapsible(False)
        self._plan_split.addWidget(self._plan_view)
        self._plan_split.addWidget(self._review)
        self._plan_split.setStretchFactor(0, 1)
        self._plan_split.setSizes([800, 320])
        self._tabs.addTab(self._plan_split, "Pohja")
        self._inspect_tab_idx = self._tabs.addTab(self._inspect_view, "3D-tarkastus")
        # Välilehteä voi klikata suoraan, jolloin `_inspect_3d` ei ajaisi
        # lainkaan ja näkymä jäisi tyhjäksi — se oli kytketty vain alapalkin
        # nappiin. Käyttäjä avasi välilehden ja näki tyhjän ruudun.
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.addTab(self._log_panel, "Loki")
        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(1, 1)

        self._result_models: list = []
        self._learner = CorrectionLearner()
        self._run_marks: list[tuple[float, str]] = []
        self._run_last = ""
        self._run_clock = QtCore.QElapsedTimer()
        self._run_tick = QtCore.QTimer(self)
        self._run_tick.setInterval(1000)
        self._run_tick.timeout.connect(self._tick_status)
        self._result_multi = False
        self._last_cfg: PipelineConfig | None = None
        self._selected: list = []

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

        # Valintapalkki (näkyy kun elementtiä klikataan pohjassa): poista/peruuta
        self._select_bar = self._build_select_bar()
        self._select_bar.setVisible(False)
        root.addWidget(self._select_bar)

        # Tulosfooter (näkyy konversion jälkeen): yhteenveto + avaa-painikkeet
        self._results_bar = self._build_results_bar()
        self._results_bar.setVisible(False)
        root.addWidget(self._results_bar)

        self._last_out: Path | None = None
        self._last_inputs: list = []

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
        # Näkyy vasta kun mallia on muokattu (poistoja) → puhtaan IFC:n voi
        # kirjoittaa myös suoraan pohjanäkymästä, ei vain Tarkistus-välilehdeltä.
        self._footer_reexport = QtWidgets.QPushButton("Kirjoita IFC uudelleen")
        self._footer_reexport.setVisible(False)
        self._footer_reexport.clicked.connect(self._on_reexport)
        row.addWidget(self._footer_reexport)
        self._inspect_btn = QtWidgets.QPushButton("Tarkasta malli 3D")
        self._inspect_btn.clicked.connect(self._inspect_3d)
        row.addWidget(self._inspect_btn)
        self._open_ifc_btn = QtWidgets.QPushButton("Avaa IFC")
        self._open_ifc_btn.clicked.connect(self._open_ifc)
        row.addWidget(self._open_ifc_btn)
        open_dir = QtWidgets.QPushButton("Avaa kansio")
        open_dir.setObjectName("linkbtn")
        open_dir.clicked.connect(self._open_folder)
        row.addWidget(open_dir)
        return bar

    def _build_select_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("panel")
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(12)
        tag = QtWidgets.QLabel("Valittu")
        tag.setStyleSheet(f"color:{TEXT};font-weight:700;")
        row.addWidget(tag)
        self._select_label = QtWidgets.QLabel("")
        self._select_label.setStyleSheet(f"color:{TEXT};font-size:13px;")
        row.addWidget(self._select_label)
        row.addStretch()
        ok_btn = QtWidgets.QPushButton("Hyväksy")
        ok_btn.clicked.connect(self._on_selected_accept)
        row.addWidget(ok_btn)
        del_btn = QtWidgets.QPushButton("Poista")
        del_btn.clicked.connect(self._on_selected_delete)
        row.addWidget(del_btn)
        cancel = QtWidgets.QPushButton("Peruuta")
        cancel.setObjectName("linkbtn")
        cancel.clicked.connect(self._clear_selection)
        row.addWidget(cancel)
        return bar

    def _element_by(self, floor_idx: int, kind: str, elem_id: str):
        if not (0 <= floor_idx < len(self._result_models)):
            return None
        m = self._result_models[floor_idx]
        if kind == "wall":
            return next((w for w in m.walls if w.id == elem_id), None)
        if kind == "column":
            return next((c for c in m.columns if c.id == elem_id), None)
        if kind == "beam":
            return next((b for b in m.beams if b.id == elem_id), None)
        return next((o for o in m.openings if o.id == elem_id), None)

    @guard
    def _on_plan_pick(self, floor_idx: int, kind: str, elem_id: str) -> None:
        if not kind:
            self._select_bar.setVisible(False)
            self._selected = []
            return
        el = self._element_by(floor_idx, kind, elem_id)
        conf = f" · luottamus {el.confidence:.2f}" if el is not None else ""
        _fi = {"wall": "Seinä", "column": "Pilari", "beam": "Palkki",
               "door": "Ovi", "window": "Ikkuna"}.get(kind, kind)
        self._select_label.setText(f"{_fi} {elem_id}{conf}")
        self._selected = [(floor_idx, kind, elem_id)]
        self._select_bar.setVisible(True)

    @guard
    def _on_selected_delete(self) -> None:
        if not self._selected:
            return
        n = sum(1 for (fi, k, i) in self._selected if self._remove_one(fi, k, i))
        if n:
            self._after_edit(n)
        self._clear_selection()

    @guard
    def _clear_selection(self) -> None:
        self._select_bar.setVisible(False)
        self._selected = []
        self._plan_view.clear_selection()

    def _on_convert(self, inputs: list, out: Path, cfg: PipelineConfig) -> None:
        self._log_panel.clear()
        self._last_out = out
        self._last_cfg = cfg
        self._last_inputs = list(inputs)
        self._select_bar.setVisible(False)
        self._results_bar.setVisible(False)
        self._stage.reset()
        self._stage.setVisible(True)
        self._stage.set_active(0)
        label = inputs[0].name if len(inputs) == 1 else f"{len(inputs)} skannia"
        self._log_panel.info(f"Aloitetaan: {label}")
        self._file_panel.set_busy(True)
        self._progress_bar.setVisible(True)
        self._run_marks = []
        self._run_last = "Käsitellään…"
        self._run_clock.start()
        self._run_tick.start()
        self._tick_status()
        self._worker.start_job(inputs, out, cfg)

    def _elapsed(self) -> float:
        return self._run_clock.elapsed() / 1000.0 if self._run_clock.isValid() else 0.0

    def _tick_status(self) -> None:
        self.statusBar().showMessage(f"{clock(self._elapsed())} · {self._run_last}")

    def _stop_clock(self) -> float:
        total = self._elapsed()
        self._run_tick.stop()
        self._run_clock.invalidate()
        return total

    @guard
    def _on_progress(self, msg: str) -> None:
        self._log_panel.info(msg)
        if self._run_clock.isValid():
            self._run_marks.append((self._elapsed(), msg))
            self._run_last = msg.strip()
            self._tick_status()
        else:
            self.statusBar().showMessage(msg)
        st = stage_for_message(msg)
        if st is not None:
            self._stage.set_active(st)

    @guard
    def _on_finished(self, result: object) -> None:
        self._file_panel.set_busy(False)
        self._progress_bar.setVisible(False)
        self._stage.set_done()
        total = self._stop_clock()
        self._log_panel.success(f"✓ Valmis — kesto {fmt_duration(total)}")
        slow = slowest_steps(self._run_marks, total)
        if slow:
            self._log_panel.info("Pisimmät vaiheet: " + " · ".join(
                f"{lbl} {fmt_duration(d)}" for lbl, d in slow))
        models = result if isinstance(result, list) else [result]
        if isinstance(result, list):
            lines = [f"{len(result)} kerrosta käsitelty:"]
            lines += [f"  kerros {i}: {m.summary()}" for i, m in enumerate(result)]
            self._log_panel.set_results("\n".join(lines))
            self._plan_view.show_models(result)
        else:
            self._log_panel.set_results(result.summary())
            self._plan_view.show_model(result)
        self._tabs.setCurrentWidget(self._plan_split)   # näytä pohja heti
        self._result_models = models
        self._result_multi = isinstance(result, list)
        self._learner = self._load_corrections()
        self._review.set_models(models, self._learner)
        self._show_results(models)
        self.statusBar().showMessage(f"Valmis — kesto {fmt_duration(total)}")

    def _corrections_path(self) -> Path | None:
        return None if self._last_out is None else self._last_out / "corrections.json"

    def _load_corrections(self) -> CorrectionLearner:
        import json
        p = self._corrections_path()
        if p is not None and p.exists():
            try:
                return CorrectionLearner.from_json(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        return CorrectionLearner()

    def _save_corrections(self) -> None:
        import json
        p = self._corrections_path()
        if p is None:
            return
        try:
            p.write_text(json.dumps(self._learner.to_json()), encoding="utf-8")
        except OSError as e:
            self._log_panel.info(f"Korjauksia ei voitu tallentaa: {e}")

    @guard
    def _on_review_select(self, floor_idx: int, kind: str, elem_id: str) -> None:
        if 0 <= floor_idx < len(self._result_models):
            self._plan_view._floor_combo.setCurrentIndex(floor_idx)
        self._plan_view.highlight(kind, elem_id)

    def _accept(self, pairs) -> int:
        n = 0
        for fi, kind, eid in pairs:
            w = self._element_by(fi, kind, eid) if kind == "wall" else None
            if w is not None and self._learner.record(w, is_real=True):
                n += 1
        if n:
            self._save_corrections()
        return n

    @guard
    def _on_review_accept(self, floor_idx: int, kind: str, elem_id: str) -> None:
        self._accept([(floor_idx, kind, elem_id)])
        self._review.mark_accepted([(floor_idx, kind, elem_id)])

    @guard
    def _on_selected_accept(self) -> None:
        if not self._selected:
            return
        self._accept(self._selected)
        self._review.mark_accepted(self._selected)
        self._clear_selection()

    def _remove_one(self, floor_idx: int, kind: str, elem_id: str) -> bool:
        if not (0 <= floor_idx < len(self._result_models)):
            return False
        m = self._result_models[floor_idx]
        if kind == "wall":
            w = next((w for w in m.walls if w.id == elem_id), None)
            if w is not None and self._learner.record(w, is_real=False):
                self._save_corrections()
            m.walls = [w for w in m.walls if w.id != elem_id]
        elif kind == "column":
            m.columns = [c for c in m.columns if c.id != elem_id]
        elif kind == "beam":
            m.beams = [b for b in m.beams if b.id != elem_id]
        else:  # door / window
            m.openings = [o for o in m.openings if o.id != elem_id]
        return True

    @guard
    def _after_edit(self, n: int) -> None:
        self._plan_view.show_models(self._result_models)
        self._review.mark_edited()
        self._footer_reexport.setVisible(True)
        self._log_panel.info(f"Poistettu {n} elementti{'ä' if n != 1 else ''}.")

    @guard
    def _on_review_delete(self, floor_idx: int, kind: str, elem_id: str) -> None:
        if self._remove_one(floor_idx, kind, elem_id):
            self._after_edit(1)

    @guard
    def _on_plan_box(self, floor_idx: int, pairs: list) -> None:
        self._selected = [(floor_idx, k, i) for (k, i) in pairs]
        self._select_label.setText(f"{len(pairs)} elementtiä valittu")
        self._select_bar.setVisible(True)

    @guard
    def _on_reexport(self) -> None:
        from scan2bim.core.ifc.writer import write_ifc, write_building_ifc
        crs = self._last_cfg.crs_epsg if self._last_cfg else 3067
        out = self._last_out
        try:
            if self._result_multi:
                for i, m in enumerate(self._result_models):
                    fd = out / f"floor_{i:02d}"; fd.mkdir(exist_ok=True)
                    write_ifc(m, fd / "model.ifc", crs_epsg=crs)
                    m.save(fd / "model.json")
                write_building_ifc(self._result_models, out / "building.ifc", crs_epsg=crs)
            else:
                write_ifc(self._result_models[0], out / "model.ifc", crs_epsg=crs)
                self._result_models[0].save(out / "model.json")
        except Exception as e:
            self._log_panel.error(f"IFC:n uudelleenkirjoitus epäonnistui: {e}")
            QtWidgets.QMessageBox.warning(self, "Virhe", str(e))
            return
        self._footer_reexport.setVisible(False)
        self._log_panel.success("✓ IFC kirjoitettu uudelleen muokatusta mallista.")
        self.statusBar().showMessage("IFC päivitetty")

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
        self._footer_reexport.setVisible(False)   # ei muokkauksia vielä
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

    @guard
    def _inspect_3d(self) -> None:
        """Näytä malli + pistepilvi 3D-tarkastus-välilehdessä."""
        if not self._result_models or not self._last_inputs:
            return
        fi = 0
        if self._result_multi:
            fi = max(0, self._plan_view._floor_combo.currentIndex())
        if not (0 <= fi < len(self._result_models)):
            fi = 0
        model_dict = self._result_models[fi].model_dump()
        # KOKO ajon pilvi, ei vain ensimmaista tiedostoa. Nakymä keskittaa
        # pilven sen omaan keskipisteeseen ja siirtaa mallin samalla
        # vektorilla; jos pilvi on eri kuin se josta malli tehtiin, offset on
        # vaara ja malli piirtyy satojen metrien paahan pilvesta. Kayttaja nakei
        # sen: 36 aseman kellarimalli leijui erillaan yhden aseman pilvesta,
        # ja juuri se asema (Kellari 001) on rakennuksen laidalla — loki
        # varoitti ettei se jaa pintoja muiden kanssa.
        self._inspect_view.set_source(model_dict, [str(p) for p in self._last_inputs])
        self._tabs.setCurrentWidget(self._inspect_view)

    def closeEvent(self, ev) -> None:
        """Sulkeminen kesken ajon ei saa jattaa orpoa taustaprosessia."""
        try:
            self._worker.stop()
        except Exception:
            pass
        try:
            self._inspect_view._drop_npz()
        except Exception:
            pass
        super().closeEvent(ev)

    @guard
    def _on_tab_changed(self, idx: int) -> None:
        """Täytä 3D-välilehti kun siihen siirrytään."""
        if idx == self._inspect_tab_idx and self._result_models:
            self._inspect_3d()

    @guard
    def _open_ifc(self) -> None:
        p = self._find_ifc()
        if p is not None:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(p)))

    @guard
    def _open_folder(self) -> None:
        if self._last_out is not None and self._last_out.exists():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self._last_out)))

    @guard
    def _on_failed(self, error: str) -> None:
        self._file_panel.set_busy(False)
        self._progress_bar.setVisible(False)
        self._stage.setVisible(False)
        total = self._stop_clock()
        self._log_panel.error(f"Virhe ({fmt_duration(total)} ajon jälkeen): {error}")
        self.statusBar().showMessage(f"Virhe {fmt_duration(total)} ajon jälkeen")
        QtWidgets.QMessageBox.critical(self, "Virhe", error)

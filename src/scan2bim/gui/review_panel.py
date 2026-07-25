"""Tarkistuslista: matalan luottamuksen elementit (tarkistettavat). Klikkaa →
korostuu pohjakuvassa. Poista → pois mallista → puhtaampi IFC. Muutosten jälkeen
IFC kirjoitetaan uudelleen."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from scan2bim.core.qa.deviation import flag_low_confidence
from scan2bim.gui.theme import TEXT_DIM

_TYPE_FI = {"wall": "seinä", "door": "ovi", "window": "ikkuna",
            "column": "pilari", "beam": "palkki"}


class ReviewPanel(QtWidgets.QWidget):
    element_selected = QtCore.Signal(int, str, str)   # floor_idx, kind, id
    delete_requested = QtCore.Signal(int, str, str)
    reexport_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._models: list = []
        self._dirty = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._info = QtWidgets.QLabel("")
        self._info.setObjectName("subtitle")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self._list = QtWidgets.QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        layout.addWidget(self._list, stretch=1)

        btn_row = QtWidgets.QHBoxLayout()
        self._del_btn = QtWidgets.QPushButton("Poista valittu")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        self._save_btn = QtWidgets.QPushButton("Kirjoita IFC uudelleen")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self.reexport_requested)
        btn_row.addWidget(self._save_btn)
        layout.addLayout(btn_row)

    def flag_count(self) -> int:
        return sum(len(flag_low_confidence(m)) for m in self._models)

    def set_models(self, models: list) -> None:
        self._models = [m for m in models if m is not None]
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._rebuild()

    def _rebuild(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        total = 0
        for fi, m in enumerate(self._models):
            for f in flag_low_confidence(m):
                total += 1
                kind = f["type"]
                fi_txt = f"K{fi} · " if len(self._models) > 1 else ""
                label = f"{fi_txt}{_TYPE_FI.get(kind, kind)} · luottamus {f['confidence']:.2f}"
                it = QtWidgets.QListWidgetItem(label)
                it.setData(QtCore.Qt.ItemDataRole.UserRole, (fi, kind, f["id"]))
                self._list.addItem(it)
        self._list.blockSignals(False)
        if total == 0:
            self._info.setText("Ei tarkistettavia — kaikki elementit ylittävät "
                               "luottamuskynnyksen. ✓")
        else:
            self._info.setText(
                f"{total} elementtiä kannattaa tarkistaa (matala luottamus). "
                "Klikkaa → korostuu pohjassa. Poista virheelliset → puhtaampi IFC."
            )
        self._del_btn.setEnabled(False)

    def _on_select(self, cur: QtWidgets.QListWidgetItem | None, _prev=None) -> None:
        self._del_btn.setEnabled(cur is not None)
        if cur is not None:
            fi, kind, eid = cur.data(QtCore.Qt.ItemDataRole.UserRole)
            self.element_selected.emit(fi, kind, eid)

    def _on_delete(self) -> None:
        cur = self._list.currentItem()
        if cur is None:
            return
        fi, kind, eid = cur.data(QtCore.Qt.ItemDataRole.UserRole)
        self.delete_requested.emit(fi, kind, eid)

    def mark_edited(self) -> None:
        """Kutsutaan kun malli muuttui (poisto) → salli IFC:n uudelleenkirjoitus."""
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._rebuild()

    def mark_saved(self) -> None:
        self._dirty = False
        self._save_btn.setEnabled(False)

"""Tarkistuslista: käy seinät läpi, hyväksy aidot ja poista väärät.

Jokainen päätös on myös label. Kun korjauksia on tarpeeksi, lista järjestyy
sen mukaan mikä TÄSSÄ rakennuksessa erottaa valeseinän aidosta
(`core/qa/project_learning.py`). Mitattu koulun kellarilla: 40 tarkistuksella
löytyi 22/28 valeseinää, kun pelkkä matalan luottamuksen lista antoi 5.8 —
ja se lista oli kellarissa vain kaksi seinää pitkä.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

import math

from scan2bim.core.qa.deviation import flag_low_confidence
from scan2bim.core.qa.project_learning import MIN_LABELS, CorrectionLearner

_TYPE_FI = {"wall": "seinä", "door": "ovi", "window": "ikkuna",
            "column": "pilari", "beam": "palkki"}


class ReviewPanel(QtWidgets.QWidget):
    element_selected = QtCore.Signal(int, str, str)   # floor_idx, kind, id
    delete_requested = QtCore.Signal(int, str, str)
    accept_requested = QtCore.Signal(int, str, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._models: list = []
        self._learner = CorrectionLearner()
        self._accepted: set[tuple[int, str, str]] = set()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._title = QtWidgets.QLabel("Tarkistus")
        self._title.setStyleSheet("font-weight:700;font-size:14px;")
        layout.addWidget(self._title)

        self._info = QtWidgets.QLabel("")
        self._info.setObjectName("subtitle")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self._list = QtWidgets.QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        layout.addWidget(self._list, stretch=1)

        btn_row = QtWidgets.QHBoxLayout()
        self._ok_btn = QtWidgets.QPushButton("Hyväksy")
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._ok_btn)
        self._del_btn = QtWidgets.QPushButton("Poista")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def set_models(self, models: list, learner: CorrectionLearner | None = None) -> None:
        self._models = [m for m in models if m is not None]
        self._learner = learner if learner is not None else CorrectionLearner()
        self._accepted = set()
        self._rebuild(select=False)

    def _flags(self):
        for fi, m in enumerate(self._models):
            for f in flag_low_confidence(m):
                yield fi, f

    def _reviewed(self, fi: int, kind: str, eid: str) -> bool:
        return (fi, kind, eid) in self._accepted or (
            kind == "wall" and self._learner.labelled(eid))

    def _ranked(self) -> list[tuple[int, object, float]]:
        floor_of = {id(w): fi for fi, m in enumerate(self._models) for w in m.walls}
        walls = [w for m in self._models for w in m.walls]
        return [(floor_of[id(w)], w, p) for w, p in self._learner.rank(walls)]

    def _rebuild(self, select: bool = True) -> None:
        keep_row = max(self._list.currentRow(), 0)
        self._list.blockSignals(True)
        self._list.clear()
        multi = len(self._models) > 1
        real, fake = self._learner.counts()
        rows: list[tuple[str, tuple[int, str, str]]] = []
        if self._learner.ready():
            # EI prosenttia: mallin P(aito) ei ole kalibroitu. Mitattu kellarilla
            # 26 korjauksen jälkeen: 10 epäilyttävimmästä 5 oli valeseiniä, mutta
            # niiden "epäily" oli keskimäärin 6 %. Järjestys pitää, luku ei.
            for rank, (fi, w, _p) in enumerate(self._ranked(), 1):
                fi_txt = f"K{fi} · " if multi else ""
                rows.append((f"{rank}. {fi_txt}seinä · {_length_m(w):.1f} m",
                             (fi, "wall", w.id)))
            self._info.setText(
                f"Opittu {real + fake} korjauksesta ({real} aitoa, {fake} väärää). "
                "Epäilyttävimmät ensin — hyväksy aidot, poista väärät. "
                "Järjestys tarkentuu jokaisesta päätöksestä.")
        else:
            listed: set[tuple[int, str, str]] = set()
            for fi, f in self._flags():
                key = (fi, f["type"], f["id"])
                if self._reviewed(*key):
                    continue
                listed.add(key)
                fi_txt = f"K{fi} · " if multi else ""
                why = f.get("reason") or f"luottamus {f['confidence']:.2f}"
                rows.append((f"{fi_txt}{_TYPE_FI.get(f['type'], f['type'])} · {why}", key))
            # Luottamus nousevasti: mitattu kellarilla paras aloitusjärjestys
            # (20 tarkistuksella 15/28 valeseinää, satunnaisella 2.4).
            rest = sorted(((fi, w) for fi, m in enumerate(self._models) for w in m.walls),
                          key=lambda t: (t[1].confidence, t[1].id))
            for fi, w in rest:
                key = (fi, "wall", w.id)
                if key in listed or self._reviewed(*key):
                    continue
                fi_txt = f"K{fi} · " if multi else ""
                rows.append((f"{fi_txt}seinä · {_length_m(w):.1f} m", key))
            left = max(MIN_LABELS - (real + fake), 0)
            if not rows:
                self._info.setText("Kaikki elementit tarkistettu. ✓")
            elif left:
                self._info.setText(
                    f"Käy seiniä läpi: hyväksy aidot, poista väärät. Vielä {left} "
                    "päätöstä, niin sovellus järjestää loput epäilyttävimmät ensin.")
            else:
                self._info.setText(
                    "Tarvitaan vielä sekä hyväksyttyjä että poistettuja seiniä, "
                    "jotta järjestys voidaan oppia.")
        for text, key in rows:
            it = QtWidgets.QListWidgetItem(text)
            it.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            self._list.addItem(it)
        self._list.blockSignals(False)
        self._title.setText(f"Tarkistus · {len(rows)} tarkistamatta" if rows else "Tarkistus")
        self._ok_btn.setEnabled(False)
        self._del_btn.setEnabled(False)
        # Seuraava rivi valitaan vain päätöksen jälkeen: silloin käyttäjä
        # etenee listaa ilman klikkausta. Latauksessa valinta panoroisi
        # pohjan pois koko rakennuksen näkymästä.
        if select and self._list.count():
            self._list.setCurrentRow(min(keep_row, self._list.count() - 1))

    def _current_key(self):
        cur = self._list.currentItem()
        return None if cur is None else cur.data(QtCore.Qt.ItemDataRole.UserRole)

    def _on_select(self, cur: QtWidgets.QListWidgetItem | None, _prev=None) -> None:
        self._del_btn.setEnabled(cur is not None)
        self._ok_btn.setEnabled(cur is not None)
        if cur is not None:
            fi, kind, eid = cur.data(QtCore.Qt.ItemDataRole.UserRole)
            self.element_selected.emit(fi, kind, eid)

    def _on_delete(self) -> None:
        key = self._current_key()
        if key is not None:
            self.delete_requested.emit(*key)

    def _on_accept(self) -> None:
        key = self._current_key()
        if key is not None:
            self.accept_requested.emit(*key)

    def mark_edited(self) -> None:
        self._rebuild()

    def mark_accepted(self, keys) -> None:
        """Hyväksytty poistuu listalta myös silloin kun siitä ei saatu labelia
        (seinältä puuttuu mitattu todiste, tai kyse on aukosta/pilarista)."""
        self._accepted.update(tuple(k) for k in keys)
        self._rebuild()


def _length_m(w) -> float:
    (x0, y0), (x1, y1) = w.axis[0][:2], w.axis[-1][:2]
    return math.hypot(x1 - x0, y1 - y0) / 1000.0

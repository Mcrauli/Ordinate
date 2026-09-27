"""Vaihekohtainen edistymisindikaattori: rivi vaihe-chippejä jotka syttyvät
ajon edetessä. Nykyinen = aksentti, valmiit = himmeä aksentti, tulevat = harmaa."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ordinate.gui.theme import ACCENT, BG_WIDGET, TEXT, TEXT_DIM

# Vaiheiden nimet + pipelinen edistymisviestien avainsanat (pieni kirjain).
_STAGES: list[tuple[str, tuple[str, ...]]] = [
    ("Lataus",       ("ladataan", "skannaustiedostoja", "kerros", "havaitaan")),
    ("Esikäsittely", ("auto-voxel", "esikäsittely", "kohinasuodatus", "pisteitä", "origoja", "keskikaista")),
    ("Suodatus",     ("semanttinen suodatin",)),
    ("Detektio",     ("seinädetektio", "pintalukitus", "qa-raportti")),
    ("IFC",          ("kirjoitetaan ifc", "koko talo", "model.ifc", "building.ifc", "dxf", "debug-pilvi")),
]


def stage_for_message(msg: str) -> int | None:
    """Palauttaa vaiheindeksin edistymisviestistä, tai None jos ei osu."""
    low = msg.lower()
    best: int | None = None
    for i, (_, keys) in enumerate(_STAGES):
        if any(k in low for k in keys):
            best = i   # viimeisin osuma voittaa (viesti voi maininta useaa)
    return best


class StageIndicator(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._chips: list[QtWidgets.QLabel] = []
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for i, (name, _) in enumerate(_STAGES):
            chip = QtWidgets.QLabel(name)
            chip.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self._chips.append(chip)
            row.addWidget(chip)
            if i < len(_STAGES) - 1:
                sep = QtWidgets.QLabel("›")
                sep.setStyleSheet(f"color:{TEXT_DIM};")
                row.addWidget(sep)
        row.addStretch()
        self.reset()

    def _style(self, chip: QtWidgets.QLabel, state: str) -> None:
        if state == "active":
            bg, fg, w = ACCENT, "#0a0e14", 700
        elif state == "done":
            bg, fg, w = "#2f5d23", TEXT, 600     # himmeä aksentti = valmis
        else:
            bg, fg, w = BG_WIDGET, TEXT_DIM, 500
        chip.setStyleSheet(
            f"background:{bg};color:{fg};border-radius:9px;"
            f"padding:3px 10px;font-size:11px;font-weight:{w};"
        )

    def reset(self) -> None:
        for c in self._chips:
            self._style(c, "pending")

    def set_active(self, index: int) -> None:
        for i, c in enumerate(self._chips):
            self._style(c, "done" if i < index else "active" if i == index else "pending")

    def set_done(self) -> None:
        for c in self._chips:
            self._style(c, "done")

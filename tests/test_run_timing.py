"""Ajon kesto ja pisimmät vaiheet käyttäjälle."""
from __future__ import annotations

from ordinate.gui.run_timing import clock, fmt_duration, slowest_steps


def test_duration_formats() -> None:
    assert fmt_duration(42) == "42 s"
    assert fmt_duration(2334) == "38 min 54 s"
    assert fmt_duration(3979) == "1 h 06 min"
    assert clock(65) == "01:05" and clock(3979) == "1:06:19"


def test_step_duration_is_time_until_the_next_message() -> None:
    marks = [(0.0, "Skannaustiedostoja: 37"),
             (41.6, "Havaitaan kerroksia…"),
             (539.3, "Semanttinen suodatin (28,599,511 pistettä)…"),
             (1051.0, "Ladataan keskikaista…"),
             (1301.7, "Ladataan 5mm-pilvi…")]
    steps = slowest_steps(marks, total=1566.1, n=2)
    assert [lbl for lbl, _ in steps] == ["Semanttinen suodatin (28,599,511 pistettä)",
                                         "Havaitaan kerroksia"]
    assert round(steps[0][1], 1) == 511.7


def test_short_steps_are_not_reported() -> None:
    assert slowest_steps([(0.0, "a"), (5.0, "b")], total=9.0) == []

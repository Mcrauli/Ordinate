"""Hidas syötelevy on kerrottava — se on iso osa ajon kestosta.

Mitattu koulun kellarilla: 31.7 GB USB-tikulta 95 MB/s, neljä lukukierrosta
= 22 min 56:sta pelkkää levyodotusta. Sama tiedosto sisäiseltä NVMe:ltä
1884 MB/s.
"""
from __future__ import annotations

from scan2bim.core.pipeline import slow_input_warning


def test_usb_stick_is_reported_with_the_wait_it_causes() -> None:
    msg = slow_input_warning(31_700.0, 95.0)
    assert msg is not None
    assert "95 MB/s" in msg
    assert "22 min" in msg          # 31700 MB * 4 / 95 / 60
    assert "SSD" in msg


def test_fast_disk_and_small_input_stay_quiet() -> None:
    assert slow_input_warning(31_700.0, 1884.0) is None
    assert slow_input_warning(50.0, 95.0) is None      # pieni skanni, ei väliä
    assert slow_input_warning(31_700.0, None) is None  # mittaus epäonnistui

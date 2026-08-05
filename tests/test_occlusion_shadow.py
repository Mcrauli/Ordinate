"""Occlusion shadow -filtterin min-yli-skannerien -logiikka.

Aito aukko: JOKIN skanneri näkee sen läpi (matala okkluusioluku) → säilyy.
Aito kalustevarjo: kaikki skannerit tukossa → hylätään.
"""
import numpy as np

from scan2bim.core.segmentation.opening_detector import _is_occlusion_shadow
from scan2bim.schemas.model import ElementSource, Opening, Wall

_SRC = ElementSource(method="histogram")
_OSRC = ElementSource(method="opening")


def _wall():
    return Wall(id="w0", confidence=1.0, source=_SRC,
                axis=[[0.0, 0.0], [4000.0, 0.0]], height=3000.0, thickness=200.0, z_min=0.0)


def _opening():
    # aukko keskellä seinää, 1000 mm leveä, lattiasta 2000 mm korkeuteen
    return Opening(id="o0", confidence=1.0, source=_OSRC, opening_type="door", wall_id="w0",
                   position_along=1500.0, width=1000.0, sill_height=0.0, opening_height=2000.0)


def _block_points(x0, x1, n=4000):
    """Pilvi kalusteesta aukon EDESSÄ (y=-500, skannerien ja seinän välissä)."""
    xs = np.random.uniform(x0, x1, n)
    zs = np.random.uniform(200.0, 1800.0, n)
    ys = np.full(n, -500.0)
    return np.column_stack([xs, ys, zs])


def test_shadow_all_scanners_blocked_rejected():
    wall, op = _wall(), _opening()
    # kaksi skanneria, molemmat seinän ETUPUOLELLA (y<0), molempien näkymä tukossa
    origins = [np.array([2000.0, -3000.0, 1500.0]), np.array([1000.0, -3000.0, 1500.0])]
    pts = _block_points(1400.0, 2600.0, 8000)
    assert _is_occlusion_shadow(op, wall, pts, origins, 0.0) is True


def test_real_opening_one_scanner_sees_through_kept():
    wall, op = _wall(), _opening()
    origins = [np.array([2000.0, -3000.0, 1500.0]), np.array([1000.0, -3000.0, 1500.0])]
    # kaluste peittää vain toisen skannerin näkymän (siirretty sivuun aukosta),
    # jättäen suoran näkölinjan aukkoon → matala min → säilyy
    pts = _block_points(2700.0, 3200.0, 8000)
    assert _is_occlusion_shadow(op, wall, pts, origins, 0.0) is False


def test_no_points_kept():
    wall, op = _wall(), _opening()
    origins = [np.array([2000.0, -3000.0, 1500.0])]
    pts = np.empty((0, 3), dtype=float)
    assert _is_occlusion_shadow(op, wall, pts, origins, 0.0) is False

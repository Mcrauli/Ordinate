"""Nurkkakoneisto ohitetaan isossa matalassa tilassa, ei muualla."""
from scan2bim.core.pipeline import _CORNER_MIN_HEIGHT, _FILTER_MIN_AREA_M2


def _use_corners(area_m2: float, free_height_mm: float) -> bool:
    """Sama sääntö kuin `_detect`issä."""
    return not (area_m2 >= _FILTER_MIN_AREA_M2 and free_height_mm < _CORNER_MIN_HEIGHT)


def test_a_large_low_space_skips_the_corner_machinery():
    """Koulun kellari: 7137 m², vapaa korkeus 1.78 m."""
    assert not _use_corners(7137.0, 1780.0)


def test_a_large_tall_space_keeps_it():
    """Liiketila ja Rohbau ovat isoja mutta korkeita — huoneita nurkkineen."""
    assert _use_corners(13064.0, 8510.0)
    assert _use_corners(1155.0, 10290.0)


def test_a_small_low_space_keeps_it():
    """Asunto ja talo ovat matalia mutta pieniä — juuri niitä varten ketju on."""
    assert _use_corners(82.0, 2700.0)
    assert _use_corners(48.0, 2820.0)

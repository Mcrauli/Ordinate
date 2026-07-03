"""remove_dangling_walls: poistaa vain TYNGAT — pitka detektoitu seina sailyy
vaikka sen paat eivat (viela) yhdy mihinkaan (nurkkien sulku tapahtuu myohemmin)."""
from scan2bim.core.semantics.wall_semantics import remove_dangling_walls
from scan2bim.schemas.model import ElementSource, Wall


def _wall(wid, x0, y0, x1, y1, method="contour"):
    return Wall(
        id=wid, confidence=1.0, classification="wall",
        source=ElementSource(method=method),
        axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=200.0, z_min=0.0,
    )


def test_long_floating_wall_kept():
    walls = [
        _wall("w_bottom", 0, 0, 8000, 0),
        _wall("w_left", 0, 0, 0, 3000),
        # pitka ylaseina jonka kumpikaan paa ei ulotu muihin (vasen seina jaa lyhyeksi)
        _wall("w_top", 200, 5500, 7800, 5500),
    ]
    kept = remove_dangling_walls(walls)
    assert any(w.id == "w_top" for w in kept), "pitka kelluva seina poistettiin"


def test_short_floating_stub_removed():
    walls = [
        _wall("w_bottom", 0, 0, 8000, 0),
        _wall("w_left", 0, 0, 0, 3000),
        _wall("w_stub", 3000, 4000, 4200, 4000),   # 1200mm tynka ilmassa
    ]
    kept = remove_dangling_walls(walls)
    assert not any(w.id == "w_stub" for w in kept), "tynka jai malliin"

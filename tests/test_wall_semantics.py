"""remove_dangling_walls: poistaa vain TYNGAT — pitka detektoitu seina sailyy
vaikka sen paat eivat (viela) yhdy mihinkaan (nurkkien sulku tapahtuu myohemmin)."""
from scan2bim.core.semantics.wall_semantics import _deduplicate, remove_dangling_walls
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


def test_reachable_wall_kept():
    # talo 000035: oikea 1.6m seina jonka GT-naapurit jaivat detektoimatta —
    # sen jatke osuu 1.7m paassa olevaan pystyseinaan (close_open_corners
    # yhdistaisi sen myohemmin) → EI saa poistaa danglingina.
    walls = [
        _wall("w_real", -3200, 200, -1600, 200),
        _wall("w_west", -4900, -1200, -4900, 300),
        _wall("w_south", -4900, -1200, -2700, -1200),
    ]
    kept = remove_dangling_walls(walls)
    assert any(w.id == "w_real" for w in kept), "yhdistettavissa oleva seina poistettiin"


def test_dedup_extends_kept_wall_to_union_span():
    # talo 000035: 8.6m itaseina — detektio loysi 2.2m patkan (conf 1.0),
    # perimetri lisasi 6.8m seinan (conf 0.5) 150mm sivussa. Dedup piti patkan
    # ja HEITTI POIS pitkan → itareuna auki. Union-janne pitaa sailyttaa.
    frag = _wall("w_frag", 5000, -1500, 5000, 700)
    perim = _wall("w_perim", 5150, 2100, 5150, -4700, method="floorplan")
    perim = perim.model_copy(update={"confidence": 0.5})
    kept = _deduplicate([frag, perim])
    assert len(kept) == 1
    ys = sorted([kept[0].axis[0][1], kept[0].axis[1][1]])
    assert ys[0] <= -4600 and ys[1] >= 2000, f"janne ei laajentunut unioniin: {kept[0].axis}"

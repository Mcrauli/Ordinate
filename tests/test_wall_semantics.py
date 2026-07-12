"""remove_dangling_walls: poistaa vain TYNGAT — pitka detektoitu seina sailyy
vaikka sen paat eivat (viela) yhdy mihinkaan (nurkkien sulku tapahtuu myohemmin)."""
from scan2bim.core.semantics.wall_semantics import (
    _deduplicate,
    merge_collinear_walls,
    remove_dangling_walls,
)
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


def test_perimeter_continuation_merges_onto_measured_line():
    # matterport-lobby: itaseina jakautui mitattuun patkaan (92mm, x~12930) ja
    # perimetrijatkeeseen (300mm, x~13045, ~150mm sivussa kontuuribiaksen takia).
    # Spanit limittyivat 507mm → pinnat 62mm SISAKKAIN nurkassa. Perimetrijatke
    # pitaa sulauttaa MITATUN seinan linjalle (ei pidemman fiktioseinan).
    meas = _wall("w_meas", 12930, -26090, 12930, -22670)
    meas = meas.model_copy(update={"thickness": 92.0, "measured_thickness": 92.0})
    perim = _wall("w_perim", 13080, -25580, 13080, -32100, method="floorplan")
    perim = perim.model_copy(update={"confidence": 0.25, "thickness": 300.0})
    out = merge_collinear_walls([meas, perim])
    assert len(out) == 1
    w = out[0]
    assert w.thickness == 92.0, f"paksuus ei mitatusta: {w.thickness}"
    assert all(abs(p[0] - 12930) < 1.0 for p in w.axis), f"akseli ei mitatulla linjalla: {w.axis}"
    ys = sorted([w.axis[0][1], w.axis[1][1]])
    assert ys[0] <= -32000 and ys[1] >= -22700, f"janne ei kata koko seinaa: {w.axis}"


def test_separate_parallel_wall_not_merged_into_perimeter():
    # Aidosti erillinen sisaseina 400mm paassa perimetrilinjasta EI saa sulautua.
    meas = _wall("w_meas", 12530, -26090, 12530, -22670)
    perim = _wall("w_perim", 12930, -25580, 12930, -32100, method="floorplan")
    out = merge_collinear_walls([meas, perim])
    assert len(out) == 2, "erillinen rinnakkaisseina sulautui virheellisesti"

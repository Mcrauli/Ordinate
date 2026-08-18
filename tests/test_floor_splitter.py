"""Kerrosjako-logiikan testit."""
import numpy as np
import pytest

from scan2bim.core.geometry.floor_splitter import detect_floors


def _make_floor_z(floor_z: float, height: float = 2800.0, n: int = 5000) -> np.ndarray:
    """Generoi Z-pisteitä yhdelle kerrokselle (lattia + seinät + katto)."""
    rng = np.random.default_rng(42)
    return rng.uniform(floor_z, floor_z + height, n).astype(np.float32)


def test_single_floor():
    z = _make_floor_z(0.0)
    floors = detect_floors(z)
    assert len(floors) == 1
    lo, hi = floors[0]
    assert lo <= 0.0
    assert hi >= 2800.0


def test_two_floors():
    z = np.concatenate([
        _make_floor_z(0.0, height=2800.0),
        _make_floor_z(3100.0, height=2800.0),  # 300mm laattaväli
    ])
    floors = detect_floors(z)
    assert len(floors) == 2
    assert floors[0][1] < floors[1][0] + 500  # ei päällekkäin (puskuri ok)


def test_three_floors():
    z = np.concatenate([
        _make_floor_z(0.0, height=3000.0),
        _make_floor_z(3300.0, height=3000.0),
        _make_floor_z(6600.0, height=3000.0),
    ])
    floors = detect_floors(z)
    assert len(floors) == 3


def test_very_short_z_returns_one_floor():
    z = np.linspace(0.0, 500.0, 100).astype(np.float32)
    floors = detect_floors(z)
    assert len(floors) == 1


def test_floor_bounds_cover_data():
    z = _make_floor_z(1000.0, height=2700.0)
    floors = detect_floors(z)
    lo, hi = floors[0]
    assert lo <= 1000.0
    assert hi >= 3700.0


def _slab(z, n=40000, rng=None):
    rng = rng or np.random.RandomState(1)
    return z + rng.normal(0, 8.0, n)


def test_sparse_ghost_floor_skipped():
    """1500 harhapistetta rakennuksen alla ei ole kerros (scene_02008:
    haamukerros tuotti tyhjan mallin IFC:hen)."""
    rng = np.random.RandomState(2)
    z = np.concatenate([
        rng.uniform(-5800, -3400, 1500),      # harhapisteet
        _slab(0, rng=rng), _slab(2800, rng=rng),
        rng.uniform(0, 2800, 60000),          # seinat
    ])
    floors = detect_floors(z)
    assert len(floors) == 1, f"kerroksia {len(floors)}, haamukerros mukana"
    lo, hi = floors[0]
    assert lo < 0 < 2800 < hi


def test_two_levels_without_empty_gap_split_at_slab():
    """Tyomaa: portaikko/aukot yhdistavat tasot → ei tyhjaa z-kaistaa.
    Jako on tehtava SISAISEN laattapiikin kohdalta (kaksi laattaparia).

    Valipohja on KAKSI pintaa: alemman kerroksen katto ja ylemman lattia.
    Mitattu aidosta kaksikerroksisesta keilauksesta (`data/raw/test_multiscan`):
    3000 ja 3296 mm. Yhden pinnan fixture ei erottaisi kerrosjakoa palkiston
    alapinnasta, joka on juuri se virhe jonka takia Rohbau site_07:aan
    keksittiin toinen kerros."""
    rng = np.random.RandomState(3)
    z = np.concatenate([
        _slab(0, rng=rng),                     # alalattia
        _slab(3000, n=60000, rng=rng),         # valipohjan alapinta (alakerran katto)
        _slab(3300, n=60000, rng=rng),         # valipohjan ylapinta (ylakerran lattia)
        _slab(6000, rng=rng),                  # ylakatto
        rng.uniform(0, 6000, 50000),           # seinat + portaikko (EI tyhjaa)
    ])
    floors = detect_floors(z)
    assert len(floors) == 2, f"kerroksia {len(floors)}, odotettiin 2"
    (l0, h0), (l1, h1) = sorted(floors)
    assert l0 < 100 and 2900 < h0 < 3700, f"alakerros {l0}..{h0}"
    assert 2500 < l1 < 3300 and h1 > 5900, f"ylakerros {l1}..{h1}"


def test_beam_soffit_is_not_a_storey_split():
    """10 m halli jossa palkiston alapinta on TIHEAMPI kuin oikea katto.

    Mitattu Rohbau3D site_07 scene_07001: alapintapiikki 2.9 M pistetta,
    kattopiikki 2.8 M. Pelkka suosio keksi toisen kerroksen palkiston kohdalle
    ja katkaisi palkit kesken (`data/_beam_qa.py`: instanssikattavuus 0.21 vs
    muiden 0.53-0.60). Yksi vaakapinta ei ole kerrosjako.
    """
    rng = np.random.RandomState(7)
    z = np.concatenate([
        _slab(0, n=90000, rng=rng),            # lattia
        _slab(7450, n=30000, rng=rng),         # palkiston alapinta, YKSI pinta
        _slab(10000, n=28000, rng=rng),        # oikea katto, heikompi
        rng.uniform(0, 10000, 60000),          # seinat + pilarit
    ])
    floors = detect_floors(z)
    assert len(floors) == 1, \
        f"palkiston alapinnasta tuli kerrosjako: {[(round(a), round(b)) for a, b in floors]}"

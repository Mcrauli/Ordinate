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


def _thick_surface(z0, thickness, n, rng):
    """Yksi pinta jonka hajonta on `thickness` — EI kahta pintaa."""
    return rng.uniform(z0, z0 + thickness, n)


def _hist(levels, n_bins=8, lo=5300.0, step=100.0):
    """Histogrammi ja sen binikeskipisteet: `levels` = {bini-indeksi: pistemaara}."""
    centers = lo + step * (np.arange(n_bins) + 0.5)
    hist = np.zeros(n_bins)
    for i, v in levels.items():
        hist[i] = v
    return centers, hist


def test_slab_pair_requires_concrete_between_the_two_surfaces():
    """Kaksi pintaa 300 mm etaisyydella JA valissa tyhjaa = valipohja."""
    from scan2bim.core.geometry.floor_splitter import _is_slab_pair
    centers, hist = _hist({0: 50000, 1: 400, 2: 300, 3: 48000})
    group = [float(centers[0]), float(centers[3])]
    assert _is_slab_pair(group, centers, hist)


def test_one_thick_surface_is_not_a_slab_pair():
    """Sama levays, mutta valissa on pisteita joka binissa = YKSI paksu pinta.

    Mitattu Rohbau scene_07000 voxelilla 20 mm: piikkiryhma z 5363..5563,
    levays 200 mm eli vanhan saannon mukaan "pintapari", mutta binit sisalla
    olivat 198868 ja 263273 — ei yhtaan tyhjaa. Betoni ei palauta pistetta.
    """
    from scan2bim.core.geometry.floor_splitter import _is_slab_pair
    centers, hist = _hist({0: 50000, 1: 46000, 2: 44000, 3: 48000})
    group = [float(centers[0]), float(centers[3])]
    assert not _is_slab_pair(group, centers, hist)


def test_slab_pair_emptiness_is_relative_to_the_group_peak():
    """Tyhjyys on OSUUS ryhman huipusta, ei pistemaara — muuten saanto muuttuu
    skannin tiheyden mukana. Sama muoto kymmenesosalla pisteita = sama tulos."""
    from scan2bim.core.geometry.floor_splitter import _is_slab_pair
    centers, hist = _hist({0: 5000, 1: 40, 2: 30, 3: 4800})
    group = [float(centers[0]), float(centers[3])]
    assert _is_slab_pair(group, centers, hist)
    centers, hist = _hist({0: 5000, 1: 4600, 2: 4400, 3: 4800})
    assert not _is_slab_pair([float(centers[0]), float(centers[3])], centers, hist)


def test_thick_beam_soffit_is_not_a_slab_pair():
    """Palkiston alapinta 200 mm hajonnalla ei ole valipohja.

    Mitattu Rohbau scene_07000 voxelilla 20 mm: piikkiryhma z 5363..5563,
    levays 200 mm eli "pintapari" — mutta ryhman sisalla ei ole yhtaan tyhjaa
    binia. Aidon laatan sisalla on umpibetoni. Ilman tyhjyysehtoa jako oli
    kiinni TIHEYDESSA: sama scene jakautui kahteen kerrokseen voxeleilla 20 ja
    40 mutta ei voxeleilla 0, 10 ja 80.
    """
    rng = np.random.RandomState(11)
    z = np.concatenate([
        _slab(0, n=90000, rng=rng),
        _thick_surface(5350, 220.0, 150000, rng),  # palkiston alapinta, paksu
        _slab(10000, n=28000, rng=rng),
        rng.uniform(0, 10000, 60000),
    ])
    floors = detect_floors(z)
    assert len(floors) == 1, \
        f"paksusta alapinnasta tuli kerrosjako: {[(round(a), round(b)) for a, b in floors]}"


def test_storey_count_does_not_change_with_point_density():
    """Sama rakennus harvennettuna: kerrosmaaran on pysyttava samana.

    Tama on yleistyvyyden ydin — tuntemattoman skannin tiheytta ei tiedeta
    etukateen. Mitattu Rohbau scene_07000: ennen tata sama scene antoi 1, 1, 2,
    2, 1 kerrosta pistevaleilla 4, 10, 17, 35 ja 70 mm.
    """
    rng = np.random.RandomState(13)
    z = np.concatenate([
        _slab(0, n=90000, rng=rng),
        _thick_surface(5350, 220.0, 150000, rng),
        _slab(10000, n=28000, rng=rng),
        rng.uniform(0, 10000, 60000),
    ])
    counts = [len(detect_floors(z[::k])) for k in (1, 2, 4, 8, 16)]
    assert len(set(counts)) == 1, f"kerrosmaara vaihteli tiheyden mukana: {counts}"

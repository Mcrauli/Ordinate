"""remove_shelf_front_walls vaatii TODISTEEN: hyllytasot seinän vieressä.

Muoto (lyhyehkö seinä pitkän rinnalla) on runkovaiheen rakennuksessa aito
kipsiseinä julkisivun edessä. Erotin on mitattu: Rohbaun GT-seinät 0-2 tasoa,
myymälän hyllynetupinnat 7-9."""
import numpy as np

from scan2bim.core.semantics.wall_semantics import remove_shelf_front_walls
from scan2bim.schemas.model import ElementSource, Wall


def _wall(x0, y0, x1, y1, thickness=200.0):
    return Wall(id=f"w_{x0}_{y0}_{x1}_{y1}", confidence=1.0, classification="wall",
                source=ElementSource(method="histogram"),
                axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=thickness,
                z_min=0.0)


def _box(w=48000, h=32000):
    return [_wall(0, 0, w, 0), _wall(w, 0, w, h), _wall(w, h, 0, h), _wall(0, h, 0, 0)]


def _surface(x, y0, y1, n=4000, rng=None):
    rng = rng or np.random.default_rng(0)
    return np.column_stack([np.full(n, float(x)) + rng.normal(0, 3.0, n),
                            rng.uniform(y0, y1, n),
                            rng.uniform(200.0, 2500.0, n)])


def _decks(x0, x1, y0, y1, levels, n=3000, rng=None):
    """Vaakatasoja ~450 mm välein — hyllykön hyllyt."""
    rng = rng or np.random.default_rng(1)
    out = []
    for i in range(levels):
        z = 300.0 + 450.0 * i
        out.append(np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n),
                                    np.full(n, z) + rng.normal(0, 5.0, n)]))
    return np.vstack(out)


def _background(x0, x1, y0, y1, n=20000, rng=None):
    """Tavaraa ja pystytukia hyllyjen välissä — ilman tätä hyllytasot OVAT
    sarakkeen mediaani eikä mikään erotu (mitattu retail_l: pohjataso 2354)."""
    rng = rng or np.random.default_rng(3)
    return np.column_stack([rng.uniform(x0, x1, n), rng.uniform(y0, y1, n),
                            rng.uniform(300.0, 2400.0, n)])


def test_shelf_with_decks_is_removed():
    walls = _box() + [_wall(900, 5000, 900, 13000)]
    pts = np.vstack([_surface(900, 5000, 13000),
                     _background(1000, 1900, 5000, 13000),
                     _decks(1000, 1900, 5000, 13000, levels=6)])
    kept = remove_shelf_front_walls(walls, retail=False, pts=pts)
    assert len(kept) == 4, "hyllytasoista huolimatta hyllyä ei poistettu"


def test_bare_wall_in_front_of_longer_wall_is_kept():
    walls = _box() + [_wall(900, 5000, 900, 13000)]
    pts = _surface(900, 5000, 13000)
    kept = remove_shelf_front_walls(walls, retail=False, pts=pts)
    assert len(kept) == 5, "aito kipsiseinä poistettiin ilman hyllytasoja"


def test_uniform_fill_beside_wall_is_not_levels():
    """Tasainen massa seinän vieressä EI ole hyllytasoja — vain toistuva rakenne on."""
    rng = np.random.default_rng(2)
    walls = _box() + [_wall(900, 5000, 900, 13000)]
    fill = np.column_stack([rng.uniform(1000, 1900, 40000),
                            rng.uniform(5000, 13000, 40000),
                            rng.uniform(300.0, 2400.0, 40000)])
    kept = remove_shelf_front_walls(walls, retail=False,
                                    pts=np.vstack([_surface(900, 5000, 13000), fill]))
    assert len(kept) == 5, "tasainen täyte luettiin hyllytasoiksi"


def test_without_points_behaviour_is_unchanged():
    walls = _box() + [_wall(900, 5000, 900, 13000)]
    assert len(remove_shelf_front_walls(walls, retail=False)) == 4


def test_single_thick_band_is_one_level():
    """Yksi paksu vaakakaista (palkki) ei ole monta tasoa — kipsiseinän välissä
    on mitatusti täsmälleen tämä."""
    rng = np.random.default_rng(4)
    walls = _box() + [_wall(900, 5000, 900, 13000)]
    band = np.column_stack([rng.uniform(1000, 1900, 15000),
                            rng.uniform(5000, 13000, 15000),
                            rng.uniform(1400.0, 1650.0, 15000)])
    pts = np.vstack([_surface(900, 5000, 13000),
                     _background(1000, 1900, 5000, 13000), band])
    kept = remove_shelf_front_walls(walls, retail=False, pts=pts)
    assert len(kept) == 5, "yksi paksu kaista luettiin hyllytasoiksi"

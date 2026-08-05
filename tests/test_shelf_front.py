"""remove_shelf_front_walls: lattia-katto-hyllyn etupinta poistetaan valeseinänä.
Retail-portitus: koko-mittainen hylly (yhtä pitkä kuin perimetri) poistetaan VAIN
liiketilassa; asunnossa aito seinä lähellä ulkoseinää (komero/erkkeri) säilyy."""
from scan2bim.core.semantics.wall_semantics import remove_shelf_front_walls
from scan2bim.schemas.model import ElementSource, Wall


def _wall(x0, y0, x1, y1, thickness=200.0):
    return Wall(id="w", confidence=1.0, classification="wall",
                source=ElementSource(method="histogram"),
                axis=[[x0, y0], [x1, y1]], height=2700.0, thickness=thickness, z_min=0.0)


def _box(w=48000, h=32000):
    """Neljä perimetriseinää → centroid on rakennuksen keskellä (ulkosuunta oikein)."""
    return [_wall(0, 0, w, 0), _wall(w, 0, w, h), _wall(w, h, 0, h), _wall(0, h, 0, 0)]


def test_full_length_shelf_removed_in_retail():
    # koko-mittainen hylly x=900 vasemman perimetrin (x=0) sisäpuolella
    walls = _box() + [_wall(900, 0, 900, 32000)]
    kept = remove_shelf_front_walls(walls, retail=True)
    xs = [round(w.axis[0][0]) for w in kept if round(w.axis[0][0]) == round(w.axis[1][0])]
    assert 900 not in xs, f"koko-mittaista hyllyä ei poistettu retailissa: {xs}"
    assert len(kept) == 4, f"pitäisi jäädä 4 perimetriseinää, jäi {len(kept)}"


def test_full_length_shelf_kept_in_residential():
    # sama geometria asunnossa (retail=False) → EI saa poistaa (voi olla aito seinä)
    walls = _box() + [_wall(900, 0, 900, 32000)]
    kept = remove_shelf_front_walls(walls, retail=False)
    assert len(kept) == 5, "asunnossa poistettiin seinä jota ei olisi saanut"


def test_short_shelf_removed_by_len_ratio():
    # lyhyt hylly (8 m) paljon pidemmän perimetrin (32 m) edessä → poistuu aina
    walls = _box() + [_wall(900, 5000, 900, 13000)]
    kept = remove_shelf_front_walls(walls, retail=False)
    assert len(kept) == 4, "lyhyt hylly pidemmän perimetrin edessä jäi poistamatta"


def test_perimeter_itself_not_removed():
    # perimetri (uloin) ei saa poistua: sen ULKOPUOLELLA ei ole rinnakkaista
    walls = _box() + [_wall(900, 0, 900, 32000)]
    kept = remove_shelf_front_walls(walls, retail=True)
    left = [w for w in kept if round(w.axis[0][0]) == 0 and round(w.axis[1][0]) == 0]
    assert left, "aito vasen perimetriseinä poistettiin"

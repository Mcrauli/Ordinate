"""Perimetriseinat: kalustevarjon reuna lattiakontuurissa EI saa tuottaa seinaa.

Sanky/sohva varjostaa lattian → kontuuriin tulee lovi keskelle huonetta.
Loven reunan ULKOpuolella huoneen katto jatkuu → se ei ole ulkoseina.
Aidon perimetrireunan ulkopuolella ei ole kattopisteita.
"""
import numpy as np

from scan2bim.core.semantics.perimeter import add_perimeter_walls


def _ceiling_pts(x0, x1, y0, y1, z, step=100.0):
    xs = np.arange(x0, x1, step)
    ys = np.arange(y0, y1, step)
    gx, gy = np.meshgrid(xs, ys)
    return np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, z)])


def test_shadow_notch_edges_rejected_real_edges_kept():
    # Huone 0..8000 x 0..6000, katto 2700 kattaa KOKO huoneen.
    # Lattiakontuurissa varjolovi: x 3000..5000, y 0..2500 (kaluste seinan vieressa).
    boundary = [
        [0.0, 0.0],
        [3000.0, 0.0],
        [3000.0, 2500.0],   # loven vasen reuna (varjo)
        [5000.0, 2500.0],   # loven pohja (varjo)
        [5000.0, 0.0],      # loven oikea reuna (varjo)
        [8000.0, 0.0],
        [8000.0, 6000.0],
        [0.0, 6000.0],
    ]
    pts = _ceiling_pts(0, 8000, 0, 6000, 2700.0)

    walls = add_perimeter_walls(boundary, [], 0.0, 2700.0, pts=pts)

    for w in walls:
        (x0, y0), (x1, y1) = w.axis
        mid = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        assert not (2500.0 < mid[0] < 5500.0 and -400.0 < mid[1] < 3000.0), (
            f"varjoloven reunasta syntyi seina: {w.id} @ {w.axis}"
        )
    # aidot reunat sailyvat (ainakin ylareuna y=6000 ja sivut)
    assert len(walls) >= 3


def test_without_points_behaves_as_before():
    boundary = [[0.0, 0.0], [8000.0, 0.0], [8000.0, 6000.0], [0.0, 6000.0]]
    walls = add_perimeter_walls(boundary, [], 0.0, 2700.0)
    assert len(walls) == 4


def test_large_hall_becomes_a_space():
    """Iso myyntialue (72x48 m) on tila, ei roskaa. Absoluuttinen 90 m2 -katto oli
    asuntokoosta johdettu ja pudotti 3456 m2 hallin kokonaan -> 0 tilaa juuri
    siella missa arkkitehti niita eniten tarvitsee."""
    from scan2bim.core.semantics.room_detector import detect_rooms
    from scan2bim.schemas.model import ElementSource, Wall

    def w(i, a, b):
        return Wall(id=f"w{i}", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"), axis=[list(a), list(b)],
                    height=7000.0, thickness=250.0, z_min=0.0)

    sx, sy = 72000.0, 48000.0
    walls = [w(0, (0, 0), (sx, 0)), w(1, (sx, 0), (sx, sy)),
             w(2, (sx, sy), (0, sy)), w(3, (0, sy), (0, 0))]
    spaces = detect_rooms(walls, 0.0, 7000.0)
    assert len(spaces) == 1, f"iso halli ei tullut tilaksi ({len(spaces)})"


def test_building_outline_still_dropped_when_it_encloses_rooms():
    """Ulkokeha jonka sisalla on ERILLINEN (kytkematon) huonerengas: polygonize
    palauttaa molemmat, ja ulkokeha on pudotettava jotta ala ei laskettaisi
    kahteen kertaan."""
    from scan2bim.core.semantics.room_detector import detect_rooms
    from scan2bim.schemas.model import ElementSource, Wall

    def w(i, a, b):
        return Wall(id=f"w{i}", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"), axis=[list(a), list(b)],
                    height=2700.0, thickness=120.0, z_min=0.0)

    outer = [((0, 0), (10000, 0)), ((10000, 0), (10000, 8000)),
             ((10000, 8000), (0, 8000)), ((0, 8000), (0, 0))]
    inner = [((3000, 3000), (6000, 3000)), ((6000, 3000), (6000, 6000)),
             ((6000, 6000), (3000, 6000)), ((3000, 6000), (3000, 3000))]
    walls = [w(i, a, b) for i, (a, b) in enumerate(outer + inner)]
    spaces = detect_rooms(walls, 0.0, 2700.0)
    areas = []
    for s in spaces:
        b = np.array(s.boundary, float)
        x, y = b[:, 0], b[:, 1]
        areas.append(abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2)
    assert all(a < 20_000_000 for a in areas), f"ulkokeha jai tilaksi: {areas}"

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


def test_hall_closed_by_floor_contour_when_wall_ring_is_broken():
    """Perimetri pirstoutuu isossa tilassa (mitattu 72x48 m myymalalla: itaseina
    5 palana, suurin rako 5.3 m) -> polygonize ei tuota myyntialuetta lainkaan.
    Lattiakontuuri on rakenteeltaan suljettu -> se sulkee graafin."""
    from scan2bim.core.semantics.room_detector import detect_rooms
    from scan2bim.schemas.model import ElementSource, Wall

    def w(i, a, b):
        return Wall(id=f"w{i}", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"), axis=[list(a), list(b)],
                    height=7000.0, thickness=250.0, z_min=0.0)

    sx, sy = 72000.0, 48000.0
    # etela ehjana, muut palasina joiden valissa metrien rakoja
    walls = [
        w(0, (0, 0), (sx, 0)),
        w(1, (sx, 0), (sx, 12000)), w(2, (sx, 30000), (sx, sy)),
        w(3, (sx, sy), (40000, sy)), w(4, (20000, sy), (0, sy)),
        w(5, (0, sy), (0, 35000)), w(6, (0, 14000), (0, 0)),
    ]
    assert detect_rooms(walls, 0.0, 7000.0) == [], "testi ei toista virhetta"

    # Kontuuri kulkee seinan ULKOpinnan tasalla (mitattu myymalalla 260 mm
    # keskilinjojen ulkopuolella). Ilman kohdistusta seinaviivat jaavat
    # kellumaan renkaan sisaan, iso kasvo saa reiat ja putoaa ulkokehana.
    o = 260.0
    ring = [(-o, -o), (sx + o, -o), (sx + o, sy + o), (-o, sy + o)]
    spaces = detect_rooms(walls, 0.0, 7000.0, boundaries=[ring])
    assert len(spaces) == 1, f"halli ei sulkeutunut ({len(spaces)})"
    b = np.array(spaces[0].boundary, float)
    x, y = b[:, 0], b[:, 1]
    area = abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2
    assert abs(area - sx * sy) / (sx * sy) < 0.02, f"ala {area/1e6:.0f} m2"


def test_floor_contour_does_not_override_wall_line():
    """Kontuuri kulkee ~puoli paksuutta seinan ulkopuolella. Tilan rajan on
    pysyttava seinan keskilinjassa - kapea kaista niiden valissa putoaa."""
    from scan2bim.core.semantics.room_detector import detect_rooms
    from scan2bim.schemas.model import ElementSource, Wall

    def w(i, a, b):
        return Wall(id=f"w{i}", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"), axis=[list(a), list(b)],
                    height=2700.0, thickness=250.0, z_min=0.0)

    sx, sy = 8000.0, 6000.0
    walls = [w(0, (0, 0), (sx, 0)), w(1, (sx, 0), (sx, sy)),
             w(2, (sx, sy), (0, sy)), w(3, (0, sy), (0, 0))]
    ring = [(-125, -125), (sx + 125, -125), (sx + 125, sy + 125), (-125, sy + 125)]
    spaces = detect_rooms(walls, 0.0, 2700.0, boundaries=[ring])
    assert len(spaces) == 1, f"kontuuri toi ylimaaraisia tiloja ({len(spaces)})"
    b = np.array(spaces[0].boundary, float)
    x, y = b[:, 0], b[:, 1]
    area = abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2
    assert abs(area - sx * sy) < 1e6, f"raja ei ole seinan keskilinjassa: {area/1e6:.2f} m2"


def test_contour_never_shrinks_a_wall_bounded_room():
    """Kontuurin sijaintiprior on heikko (25 mm ruudukko + dilaatio). Se saa VAIN
    taydentaa, ei leikata: seinien rajaamat tilat on jaatava tasmalleen ennalleen.
    Ilman tata rajausta asunnon huoneala putosi 55.73 -> 53.62 m2."""
    from scan2bim.core.semantics.room_detector import detect_rooms
    from scan2bim.schemas.model import ElementSource, Wall

    def w(i, a, b):
        return Wall(id=f"w{i}", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"), axis=[list(a), list(b)],
                    height=2700.0, thickness=120.0, z_min=0.0)

    sx, sy = 9000.0, 7000.0
    walls = [w(0, (0, 0), (sx, 0)), w(1, (sx, 0), (sx, sy)),
             w(2, (sx, sy), (0, sy)), w(3, (0, sy), (0, 0)),
             w(4, (4000, 0), (4000, sy))]
    base = detect_rooms(walls, 0.0, 2700.0)
    assert len(base) == 2

    # kontuuri vinossa/kutistuneena sisaan: EI saa vaikuttaa
    ring = [(300, 250), (sx - 200, 250), (sx - 200, sy - 300), (300, sy - 300)]
    with_ring = detect_rooms(walls, 0.0, 2700.0, boundaries=[ring])
    assert [s.boundary for s in with_ring] == [s.boundary for s in base], \
        "kontuuri muutti seinien rajaamaa tilaa"


def test_contour_only_space_must_be_substantial():
    """Kontuurin varassa oleva tila on sellainen jota MIKAAN seina ei sulje ->
    sita ei ole voitu varmistaa seinaevidenssilla. Mitattu apt2: ilman korkeampaa
    rimaa syntyi 0.86 x 2.54 m "huone" vaarin sijoittuneen perimetriseinan ja
    aidon seinan valiin."""
    from scan2bim.core.semantics.room_detector import detect_rooms
    from scan2bim.schemas.model import ElementSource, Wall

    def w(i, a, b):
        return Wall(id=f"w{i}", confidence=1.0, classification="wall",
                    source=ElementSource(method="contour"), axis=[list(a), list(b)],
                    height=2700.0, thickness=120.0, z_min=0.0)

    # L-kirjaimen muotoinen seinajoukko: sulkee ison huoneen, jattaa reunaan
    # 860 mm kapean kaistan jonka vain kontuuri sulkee.
    walls = [w(0, (0, 0), (9000, 0)), w(1, (9000, 0), (9000, 7000)),
             w(2, (9000, 7000), (0, 7000)), w(3, (0, 7000), (0, 0))]
    ring = [(-860, -100), (9100, -100), (9100, 7100), (-860, 7100)]
    spaces = detect_rooms(walls, 0.0, 2700.0, boundaries=[ring])
    for s in spaces:
        b = np.array(s.boundary, float)
        assert b[:, 0].min() > -500, f"kapea reunakaista tuli tilaksi: {s.boundary}"

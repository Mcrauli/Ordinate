"""Pilaridetektio: pystypeittopohjainen — tyomaan holvituet/tavara eivat saa
ketjuttaa pilaria muuhun kramaan (DBSCAN eps teki niin -> 0/92 pilaria)."""
import numpy as np
import open3d as o3d

from scan2bim.core.segmentation.column_detector import detect_columns
from scan2bim.schemas.model import ElementSource, Wall

_RNG = np.random.RandomState(13)


def _wall(wid, x0, y0, x1, y1):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="contour"),
                axis=[[x0, y0], [x1, y1]], height=3000.0, thickness=200.0, z_min=0.0)


def _box(x, y, w, d, z0, z1, n):
    return np.column_stack([
        _RNG.uniform(x - w/2, x + w/2, n),
        _RNG.uniform(y - d/2, y + d/2, n),
        _RNG.uniform(z0, z1, n),
    ])


def _cloud(parts):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pc


def test_column_found_despite_adjacent_props_and_clutter():
    parts = [
        _box(4000, 2500, 8000, 5000, 0, 50, 20000),         # LATTIA (aito skanni)
        _box(3000, 2500, 400, 400, 50, 2950, 9000),         # AITO pilari 400x400
        _box(3800, 2500, 70, 70, 0, 2950, 800),             # holvituki 0.8m paassa
        _box(4300, 2500, 70, 70, 0, 2950, 800),             # holvituki
        _box(3600, 3200, 1200, 900, 0, 900, 4000),          # tavarakasa (matala)
        _box(2400, 2500, 70, 70, 0, 2950, 800),             # holvituki toisella puolen
    ]
    walls = [_wall("w0", 0, 0, 8000, 0), _wall("w1", 0, 5000, 8000, 5000)]
    cols = detect_columns(_cloud(parts), walls, floor_z=0.0, ceiling_z=3000.0)
    assert len(cols) == 1, f"pilareita {len(cols)}, odotettiin 1 (tuet/kasa eivat ole pilareita)"
    c = cols[0]
    assert abs(c.location[0] - 3000) < 150 and abs(c.location[1] - 2500) < 150
    assert 250 <= c.profile.width <= 550, f"profiili {c.profile.width}"


def test_low_stack_not_column():
    parts = [_box(3000, 2500, 500, 500, 0, 1200, 6000)]      # matala pino
    walls = [_wall("w0", 0, 0, 8000, 0)]
    cols = detect_columns(_cloud(parts), walls, floor_z=0.0, ceiling_z=3000.0)
    assert len(cols) == 0, "matala pino tulkittiin pilariksi"


def test_free_standing_column_simple_room():
    parts = [
        _box(3000, 2000, 6000, 4000, 0, 50, 15000),          # LATTIA (aito skanni)
        _box(2000, 2000, 300, 300, 50, 2950, 8000),
        _box(500, 3000, 900, 600, 0, 750, 2500),             # poyta
    ]
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 4000, 6000, 4000)]
    cols = detect_columns(_cloud(parts), walls, floor_z=0.0, ceiling_z=3000.0)
    assert len(cols) == 1, f"pilareita {len(cols)}"


def test_undetected_wall_fragment_not_column():
    """Detektoimatta jaaneen seinan palat: pystytaytto tayttyy, mutta linjassa
    on LISAA seinasoluja → rengastesti hylkaa (aito pilari on irrallaan)."""
    parts = [
        _box(1000, 2500, 500, 150, 0, 2950, 3000),   # seinapala 1
        _box(1800, 2500, 500, 150, 0, 2950, 3000),   # seinapala 2 samassa linjassa
        _box(2600, 2500, 500, 150, 0, 2950, 3000),   # seinapala 3
    ]
    walls = [_wall("w0", 0, 0, 8000, 0)]
    cols = detect_columns(_cloud(parts), walls, floor_z=0.0, ceiling_z=3000.0)
    assert len(cols) == 0, f"seinapalat tulkittiin {len(cols)} pilariksi"


def test_varying_cross_section_not_column():
    """Kasattu kaluste: poikkileikkaus heiluu korkeuden mukaan (ohut ala, levea
    ylaosa) — aito pilari on ~sama joka korkeudella. 3DSES-huoneen valepilari."""
    parts = [
        _box(3000, 2500, 6000, 4000, 0, 50, 15000),          # lattia
        _box(3000, 2500, 80, 80, 300, 1500, 2500),           # ohut alaosa 80mm
        _box(3000, 2500, 500, 500, 1500, 2700, 9000),        # levea ylaosa 500mm
    ]
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 4000, 6000, 4000)]
    cols = detect_columns(_cloud(parts), walls, floor_z=0.0, ceiling_z=3000.0)
    assert len(cols) == 0, f"heiluva poikkileikkaus tulkittiin {len(cols)} pilariksi"


def test_full_height_cabinet_in_clutter_not_column():
    """Tayskorkea kaappi kiinni muussa massassa: vakaa poikkileikkaus (nayttaa
    pilarilta) MUTTA vyotarokorkeudella ymparilla on tavaraa joka suunnassa —
    aito pilari on irrallaan. 3DSES-huoneen c1/c2."""
    parts = [
        _box(3000, 2500, 6000, 4000, 0, 50, 15000),          # lattia
        _box(3000, 2500, 350, 350, 50, 2900, 9000),          # "kaappi" 350x350 taysi
        # ymparoiva tavara vyotarolla (1.0-1.8m) joka suunnassa ~500mm paassa:
        _box(3000, 1950, 400, 300, 1000, 1800, 3000),
        _box(3000, 3050, 400, 300, 1000, 1800, 3000),
        _box(2450, 2500, 300, 400, 1000, 1800, 3000),
        _box(3550, 2500, 300, 400, 1000, 1800, 3000),
    ]
    walls = [_wall("w0", 0, 0, 6000, 0), _wall("w1", 0, 4000, 6000, 4000)]
    cols = detect_columns(_cloud(parts), walls, floor_z=0.0, ceiling_z=3000.0)
    assert len(cols) == 0, f"massaan kiinni oleva kaappi tulkittiin {len(cols)} pilariksi"

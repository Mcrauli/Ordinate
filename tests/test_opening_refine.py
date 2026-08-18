"""Aukon reunatarkennus: 30mm-gridin kvantisoimat reunat vedetaan raakapisteista
mm-tasolle (step-sovitus: tyhja aukko vs tayси seinapinta)."""
import numpy as np

from scan2bim.core.segmentation.opening_detector import detect_openings
from scan2bim.schemas.model import ElementSource, Wall

_RNG = np.random.RandomState(11)


class _Cloud:
    def __init__(self, pts):
        self.points = pts


def _wall_with_window(win_a0, win_a1, sill, head, L=4000.0, th=150.0, n=120000):
    """Seina y=0-tasossa x 0..L, ikkuna [win_a0,win_a1] x [sill,head]."""
    x = _RNG.uniform(0, L, n)
    z = _RNG.uniform(0, 2700, n)
    keep = ~((x > win_a0) & (x < win_a1) & (z > sill) & (z < head))
    x, z = x[keep], z[keep]
    y = th / 2.0 + _RNG.normal(0, 2.0, len(x))   # yksi pinta +75mm
    pts = np.column_stack([x, y, z])
    w = Wall(id="w0", confidence=1.0, classification="wall",
             source=ElementSource(method="contour"),
             axis=[[0.0, 0.0], [L, 0.0]], height=2700.0, thickness=th, z_min=0.0)
    return w, _Cloud(pts)


def test_window_edges_refined_to_mm():
    # HUOM: sarakedetektio vaatii sokkelin < ~600mm (lattiakaista 150-1400,
    # fb_frac 0.45) — korkeasokkeliset ikkunat ovat tunnettu puute (roadmap).
    win = (1618.0, 2531.0, 512.0, 2405.0)     # ei-gridilinjassa olevat reunat
    w, cloud = _wall_with_window(*win)
    ops = detect_openings([w], cloud, floor_z=0.0)
    assert len(ops) == 1, f"aukkoja {len(ops)}"
    op = ops[0]
    a0 = op.position_along
    a1 = a0 + op.width
    sill = op.sill_height
    head = sill + op.opening_height
    assert abs(a0 - win[0]) < 8.0, f"vasen reuna {a0:.1f} vs {win[0]}"
    assert abs(a1 - win[1]) < 8.0, f"oikea reuna {a1:.1f} vs {win[1]}"
    assert abs(sill - win[2]) < 8.0, f"silli {sill:.1f} vs {win[2]}"
    assert abs(head - win[3]) < 8.0, f"ylitys {head:.1f} vs {win[3]}"
    assert op.opening_type == "window"


def test_wide_rough_opening_is_found():
    """Runkovaiheen oviaukko on leveampi kuin asunnon ovi.

    Mitattu Rohbau3D:n GT:ta vasten: 2.5-3.0 m aukot jaivat kiinteaan
    2500 mm kattoon. Suhteellinen katto (_MAX_FRACTION 50 % seinasta) hoitaa
    varsinaisen rajauksen, joten absoluuttinen luku sai olla auliimpi.
    Scene_07000 5/35 -> 6/35 ja tarkkuus 0.312 -> 0.353, scene_07003
    2/19 -> 3/19 ja 0.500 -> 0.600; asunto ja liiketila eivat muuttuneet.
    """
    w, cloud = _wall_with_window(1200.0, 4000.0, 60.0, 2350.0, L=9000.0, n=240000)
    ops = detect_openings([w], cloud, floor_z=0.0)
    assert len(ops) == 1, f"aukkoja {len(ops)}"
    assert 2600 < ops[0].width < 3000, f"leveys {ops[0].width:.0f}"

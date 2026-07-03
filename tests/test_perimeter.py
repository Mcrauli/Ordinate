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

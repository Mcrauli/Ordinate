"""Okkluusiotesti: kolmiorajaus antaa samat osumaluvut kuin koko pilvi.

Rajaus on geometrisesti tarkka: aukkoon osuva piste on aina aseman ja aukon
välisen kolmion sisällä. Testi tihentää pisteitä juuri kolmion reunoille,
joissa väärä rajaus näkyisi.
"""
from __future__ import annotations

import numpy as np

from ordinate.core.geometry.xy_index import XYIndex
from ordinate.core.segmentation.opening_detector import _occlusion_counts
from ordinate.schemas.model import ElementSource, Opening, Wall


def test_triangle_prefilter_gives_identical_counts() -> None:
    rng = np.random.default_rng(11)
    wall = Wall(id="w", confidence=0.9, source=ElementSource(method="contour"),
                axis=[[0.0, 0.0], [20_000.0, 0.0]], height=2700.0, thickness=150.0, z_min=0.0)
    origins = [np.array([rng.uniform(-5_000, 25_000), rng.uniform(1_500, 15_000), 1_600.0])
               for _ in range(12)]
    origins.append(np.array([10_000.0, 30.0, 1_600.0]))      # liian lähellä seinää
    pts = np.column_stack([rng.uniform(-8_000, 28_000, 400_000),
                           rng.uniform(-3_000, 18_000, 400_000),
                           rng.uniform(0, 2_700, 400_000)])
    # tihennys kolmioiden reunoille
    edge = []
    for S in origins[:6]:
        for end in (4_000.0, 5_500.0):
            t = rng.uniform(0.05, 0.99, 3_000)[:, None]
            e = np.array([end, 0.0])
            xy = S[:2] + t * (e - S[:2]) + rng.normal(0, 3, (3_000, 2))
            edge.append(np.column_stack([xy, rng.uniform(0, 2_700, 3_000)]))
    pts = np.vstack([pts] + edge)
    index = XYIndex(pts)
    for pos, width, sill, h in ((4_000.0, 1_500.0, 0.0, 2_000.0),
                                (12_000.0, 900.0, 900.0, 1_200.0),
                                (18_500.0, 1_400.0, 0.0, 2_100.0)):
        op = Opening(id="o", confidence=0.5, source=ElementSource(method="opening"),
                     wall_id="w", opening_type="door", position_along=pos, width=width,
                     sill_height=sill, opening_height=h)
        full = _occlusion_counts(op, wall, pts, origins, 0.0, None)
        tri = _occlusion_counts(op, wall, pts, origins, 0.0, index)
        assert full == tri
        assert any(c > 0 for c in full[0])


def test_early_stop_gives_the_same_decision() -> None:
    from ordinate.core.segmentation.opening_detector import _is_occlusion_shadow

    rng = np.random.default_rng(5)
    wall = Wall(id="w", confidence=0.9, source=ElementSource(method="contour"),
                axis=[[0.0, 0.0], [20_000.0, 0.0]], height=2700.0, thickness=150.0, z_min=0.0)
    behind = np.column_stack([rng.uniform(-8_000, 28_000, 200_000),
                              rng.uniform(-6_000, -200, 200_000),
                              rng.uniform(0, 2_700, 200_000)])
    block = np.column_stack([rng.uniform(4_000, 5_500, 60_000), rng.uniform(2_500, 3_500, 60_000),
                             rng.uniform(0, 2_200, 60_000)])
    pts = np.vstack([behind, block])
    index = XYIndex(pts)
    op = Opening(id="o", confidence=0.5, source=ElementSource(method="opening"),
                 wall_id="w", opening_type="door", position_along=4_000.0, width=1_500.0,
                 sill_height=0.0, opening_height=2_000.0)
    # Edessä olevat asemat katsovat esteen läpi; sivuasema (kulma 47° seinän
    # normaalista, eli informatiivinen) näkee aukon esteen ohi.
    front = [np.array([4_750.0 + dx, y, 1_600.0]) for dx, y in ((0, 5_000), (-50, 6_000),
                                                                   (50, 7_000))]
    side = np.array([9_000.0, 4_000.0, 1_600.0])
    cases = {"kaikki tukossa": front, "yksi näkee ohi": [front[0], side, front[1], front[2]]}
    decisions = {}
    for name, origins in cases.items():
        full = _occlusion_counts(op, wall, pts, origins, 0.0, None)
        expect = bool(full[0]) and min(full[0]) >= full[1]
        got = _is_occlusion_shadow(op, wall, pts, origins, 0.0, index)
        assert got == expect, name
        decisions[name] = got
    assert decisions == {"kaikki tukossa": True, "yksi näkee ohi": False}, decisions

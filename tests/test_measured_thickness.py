"""`measured_thickness` saa olla asetettu VAIN kun kaksi pintaa on mitattu.

Kentta menee IFC:hen `Ordinate_Mittaus`-psetin `MitattuPaksuus_mm`:aan, eli se
on mittausvaite. `_snap_delivery_thickness` kirjoitti sen jokaiselle seinalle
snappia edeltavasta paksuudesta riippumatta siita mista paksuus oli perasin —
myos silloin kun se oli `_TL_ONE_SIDED_T`-vakio 200 mm.

Mitattu synteettisella myymalalla (GT tunnettu): nelja ulkoseinaa ovat 250 mm
ja malli vaitti mitatusti 200/200/120/200 mm luottamuksella 1.00, kun kaikki
viisi kaksipuolista sisaseinaa olivat tasmalleen oikein. Yksipuolisesta
seinasta on keilattu vain sisapinta — sen paksuutta EI VOI mitata, ja
kellarissa se koskee 35 perimetriseinaa jotka kaikki vaittivat 60 mm.
"""
from __future__ import annotations

import numpy as np
import pytest

from ordinate.core import pipeline as PL
from ordinate.schemas.model import ElementSource, Wall

_H = 2700.0


class _Cloud:
    def __init__(self, pts):
        self.points = np.asarray(pts, float)


def _wall(thickness=200.0, length=6000.0):
    return Wall(id="w", confidence=1.0, classification="wall",
                source=ElementSource(method="contour"),
                axis=[[0.0, 0.0], [length, 0.0]], height=_H, thickness=thickness,
                z_min=0.0)


def _face(y, length=6000.0, step=20.0, z_lo=300.0, z_hi=_H - 300.0):
    xs = np.arange(0.0, length, step)
    zs = np.arange(z_lo, z_hi, step)
    xy = np.column_stack([np.repeat(xs, len(zs)), np.full(len(xs) * len(zs), y)])
    return np.column_stack([xy, np.tile(zs, len(xs))])


def _lock(wall, pts):
    return PL._thickness_lock_walls([wall], _Cloud(pts), iters=1)[0]


def test_kaksipuolinen_saa_mittausarvon():
    """Molemmat pinnat keilattu 200 mm etaisyydella → mittaus on olemassa."""
    pts = np.vstack([_face(-100.0), _face(+100.0)])
    w = _lock(_wall(), pts)
    assert w.measured_thickness is not None
    assert abs(w.measured_thickness - 200.0) < 5.0, w.measured_thickness


def test_yksipuolinen_ei_saa_mittausarvoa():
    """Vain sisapinta keilattu → paksuus on oletus, ei mittaus."""
    w = _lock(_wall(), _face(-100.0))
    assert w.measured_thickness is None, (
        f"yksipuolinen seina vaittaa mitattua paksuutta {w.measured_thickness}")


def test_snap_ei_keksi_mittausarvoa():
    """Toimituspaksuuden snap ei saa luoda mittausvaitetta tyhjasta."""
    w = _wall(thickness=205.0)
    assert w.measured_thickness is None
    out = PL._snap_delivery_thickness([w], _Cloud(np.zeros((0, 3))))[0]
    assert out.measured_thickness is None
    assert out.thickness == 200.0, "snap standardiin ei toiminut"


def test_snap_sailyttaa_mitatun_arvon():
    w = _wall(thickness=205.0).model_copy(update={"measured_thickness": 205.0})
    out = PL._snap_delivery_thickness([w], _Cloud(np.zeros((0, 3))))[0]
    assert out.measured_thickness == 205.0
    assert out.thickness == 200.0


def test_ifc_jattaa_mittauspsetin_pois_kun_arvoa_ei_ole():
    """Kirjoittaja portittaa psetin `measured_thickness is not None`-ehdolla."""
    import inspect

    from ordinate.core.ifc import writer
    src = inspect.getsource(writer)
    i = src.index("Ordinate_Mittaus")
    ehto = src[max(0, i - 400):i]
    assert "measured is not None" in ehto, (
        "mittauspsetin portti on kadonnut — yksipuolinen seina paatyisi IFC:hen "
        "mittausvaitteena")


def test_aiempi_mittaus_kumoutuu_jos_seina_osoittautuu_yksipuoliseksi():
    """`_thickness_lock_walls` ajaa kolme kierrosta. Jos kierros 1 mittaa parin
    ja myohempi kierros paatyy yksipuoliseen polkuun, vanha mittausarvo EI saa
    jaada roikkumaan — muuten seina vaittaa mittausta jonka putki itse kumosi."""
    w = _wall().model_copy(update={"measured_thickness": 200.0})
    out = _lock(w, _face(-100.0))
    assert out.measured_thickness is None, (
        f"vanha mittausarvo {out.measured_thickness} jai voimaan vaikka "
        "lukitus paatyi yksipuoliseen polkuun")


def test_valepari_kumoaa_mittauksen():
    """Kun runkotesti hylkaa parin (toinen 'pinta' on kaluste huoneessa),
    paksuus on `_TL_ONE_SIDED_T`-vakio eika mittaus."""
    w = _wall(thickness=200.0).model_copy(update={"measured_thickness": 200.0})
    pts = np.vstack([_face(-100.0), _face(+100.0)])
    ceil = np.column_stack([
        np.repeat(np.arange(0.0, 6000.0, 50.0), 5),
        np.tile(np.linspace(-95.0, 95.0, 5), len(np.arange(0.0, 6000.0, 50.0))),
    ])
    ceil = np.column_stack([ceil, np.full(len(ceil), _H)])
    out = PL._thickness_lock_walls([w], _Cloud(pts), iters=1, ceiling_xy=ceil)[0]
    if out.thickness == PL._TL_ONE_SIDED_T and out.thickness != 200.0:
        assert out.measured_thickness is None


def test_tueton_paksuus_kumoaa_mittauksen():
    """`_unsupported_thickness_lock`: kontuurimaskin levinnyt viiva tuotti
    66 mm 'paksuuden' jota yksikaan pinta ei tue. Tulos on vakio
    `_TL_ONE_SIDED_T`, siis oletus — ei mittaus."""
    centers = np.arange(-200.0, 200.0, 2.0)
    hist = np.zeros(len(centers))
    hist[np.argmin(np.abs(centers - 30.0))] = 1000.0
    pks = np.array([int(np.argmin(np.abs(centers - 30.0)))])
    w = _wall(thickness=66.0).model_copy(update={"measured_thickness": 66.0})
    out = PL._unsupported_thickness_lock(
        w, hist, centers, pks, np.array([0.0, 1.0]),
        np.array([0.0, 0.0]), np.array([6000.0, 0.0]),
        inward=np.array([0.0, -1000.0]))
    assert out.thickness == PL._TL_ONE_SIDED_T
    assert out.measured_thickness is None, (
        f"vakiopaksuus {out.thickness} kirjattiin mittaukseksi "
        f"{out.measured_thickness}")

"""Kollineaariset palaset sulautuvat kun railossa ON seinapintaa — muttei ovesta yli.

Mitattu retail_l:sta: malli antaa 36 seinaobjektia yhdeksalle GT-seinalle.
27/29 "ylimaaraisesta" on 0-225 mm paassa GT-linjasta kulmaerolla 0.00°, ja
niiden valissa on 21 railoa joista 18 on TASMALLEEN 660 mm. Jokaisessa on
seinapinta. Railo putosi kahden saannon valiin:

  merge_collinear_walls   kohtisuora <= 130 mm, railo <=  450 mm  -> RAILO esti
  bridge_lintel_gaps      kohtisuora <=  25 mm, railo 300-2200 mm -> KOHTISUORA esti

Raja `_COLIN_GAP_EVID_MM` = 800 mm on FYSIKAALINEN eika viritetty: kapein
oviaukko on 800 mm. Sita kapeampi railo jonka kohdalla on seinapintaa ei voi
olla aukko. Suljettu ovilehti tayttaa railon pinnalla, joten pelkka
pintaevidenssi ilman leveysrajaa sulauttaisi seinan aukon yli.
"""
from __future__ import annotations

import numpy as np

from scan2bim.core.semantics.wall_semantics import (
    _COLIN_GAP_EVID_MM, _COLIN_GAP_MM, merge_collinear_walls,
)
from scan2bim.schemas.model import ElementSource, Wall

_H = 3000.0


def _wall(wid, x0, x1, y=0.0, thickness=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="contour"),
                axis=[[x0, y], [x1, y]], height=_H, thickness=thickness, z_min=0.0)


def _surface(x0, x1, y=0.0, step=25.0):
    """Pystypinta valilla [x0,x1] koko korkeudelta."""
    xs = np.arange(x0, x1, step)
    zs = np.arange(60.0, _H - 60.0, step)
    xy = np.column_stack([np.repeat(xs, len(zs)), np.full(len(xs) * len(zs), y)])
    return np.column_stack([xy, np.tile(zs, len(xs))])


def test_railo_jossa_on_pintaa_sulautuu():
    """660 mm railo pinnan kanssa — tasmalleen retail_l:n mitattu tapaus."""
    walls = [_wall("a", 0.0, 5000.0), _wall("b", 5660.0, 11000.0)]
    pts = _surface(0.0, 11000.0)
    out = merge_collinear_walls(walls, pts)
    assert len(out) == 1, f"railo jossa on pintaa jai sulauttamatta: {len(out)}"
    xs = sorted(p[0] for p in out[0].axis)
    assert xs[0] == 0.0 and xs[1] == 11000.0


def test_railo_ilman_pintaa_ei_sulaudu():
    """Sama railo tyhjana — aukko pysyy aukkona."""
    walls = [_wall("a", 0.0, 5000.0), _wall("b", 5660.0, 11000.0)]
    pts = np.vstack([_surface(0.0, 5000.0), _surface(5660.0, 11000.0)])
    assert len(merge_collinear_walls(walls, pts)) == 2


def test_ovea_leveampi_railo_ei_sulaudu_vaikka_pintaa_olisi():
    """Suljettu ovilehti tayttaa railon pinnalla — leveysraja suojaa aukon.

    Railo on 1000 mm eli tavallinen oviaukko. Luku on kirjoitettu tahan
    ABSOLUUTTISENA: jos se johdettaisiin `_COLIN_GAP_EVID_MM`:sta, testi
    liikkuisi vakion mukana eika voisi koskaan kaataa sen nostoa.
    """
    assert _COLIN_GAP_EVID_MM < 1000.0, "raja on kasvanut oviaukon levyiseksi"
    walls = [_wall("a", 0.0, 5000.0), _wall("b", 6000.0, 11000.0)]
    pts = _surface(0.0, 11000.0)
    assert len(merge_collinear_walls(walls, pts)) == 2


def test_ilman_pilvea_kayttaytyy_kuten_ennen():
    """`pts=None` → vanha saanto tasmalleen: vain <=450 mm railo sulautuu."""
    kapea = [_wall("a", 0.0, 5000.0), _wall("b", 5000.0 + _COLIN_GAP_MM - 50.0, 9000.0)]
    leveä = [_wall("a", 0.0, 5000.0), _wall("b", 5660.0, 11000.0)]
    assert len(merge_collinear_walls(kapea)) == 1
    assert len(merge_collinear_walls(leveä)) == 2


def test_eri_linjalla_ei_sulaudu_vaikka_railossa_on_pintaa():
    """Kohtisuora toleranssi pysyy voimassa: 300 mm sivussa ei ole sama seina."""
    walls = [_wall("a", 0.0, 5000.0, y=0.0), _wall("b", 5660.0, 11000.0, y=300.0)]
    pts = _surface(0.0, 11000.0)
    assert len(merge_collinear_walls(walls, pts)) == 2


def _slab(x0, x1, y=0.0, step=25.0):
    """Lattia ja katto — vaakapintaa, ei seinaa."""
    xs = np.arange(x0, x1, step)
    ys = np.arange(y - 200.0, y + 200.0, step)
    xy = np.array([(x, yy) for x in xs for yy in ys])
    out = []
    for zz in (20.0, _H - 20.0):
        out.append(np.column_stack([xy, np.full(len(xy), zz)]))
    return np.vstack(out)


def test_railo_jossa_on_vain_lattiaa_ja_kattoa_ei_sulaudu():
    """Vyotarorajaus: railo jonka tayttaa laatta EI ole seinaa.

    Ilman rajausta lattia ja katto tayttavat jokaisen railon jokaisessa
    rakennuksessa ja pintaehto olisi aina tosi — sama ansa jonka
    `flatness_prune` ja jatkuvuus ovat jo kohdanneet.
    """
    walls = [_wall("a", 0.0, 5000.0), _wall("b", 5660.0, 11000.0)]
    pts = np.vstack([_surface(0.0, 5000.0), _surface(5660.0, 11000.0),
                     _slab(5000.0, 5660.0)])
    assert len(merge_collinear_walls(walls, pts)) == 2

"""Skannerin origon yksikko luetaan PISTEISTA, ei origon etaisyydesta nollasta.

Vanha ehto oli `norm(translation) < 200 -> metreja`. Se mittaa rakennuksen
SIJAINTIA: paikallisessa ruudukossa oleva kohde on satojen metrien paassa
origosta, jolloin metripose jaa skaalaamatta ja origo on 1000x pielessa.
Mitattu koulun kellarilla (37 asemaa, asemat noin 200 m / 541 m): kertoimella
1 osui mallin alueelle 0/37, kertoimella 1000 kaikki 37.

Origoja kayttavat `remove_walls_beyond_scan_range` ja aukkojen okkluusiotesti,
joten vaara yksikko joko poistaa seinia tai kytkee suodatuksen hiljaa pois.
"""
from __future__ import annotations

import numpy as np
import pytest

from scan2bim.core.geometry.loader import scanner_origins

pye57 = pytest.importorskip("pye57")


def _write(path, pts, translation):
    e = pye57.E57(str(path), mode="w")
    try:
        e.write_scan_raw(
            {"cartesianX": np.ascontiguousarray(pts[:, 0]),
             "cartesianY": np.ascontiguousarray(pts[:, 1]),
             "cartesianZ": np.ascontiguousarray(pts[:, 2])},
            name="s0", rotation=np.array([1.0, 0.0, 0.0, 0.0]),
            translation=np.asarray(translation, dtype=float))
    finally:
        del e
    return path


def _room(scale: float, n: int = 4000):
    """Huone 6 x 4 x 2.5 m annetussa yksikossa (1.0 = metrit, 1000.0 = mm)."""
    rng = np.random.default_rng(0)
    return rng.random((n, 3)) * np.array([6.0, 4.0, 2.5]) * scale


def test_metripose_kaukana_origosta_skaalataan(tmp_path):
    """Kellarin tapaus: asema (200 m, 541 m), normi 576 > vanha raja 200."""
    f = _write(tmp_path / "kaukana.e57", _room(1.0), [200.0, 541.0, 7.8])
    o = scanner_origins(f)
    assert len(o) == 1
    assert np.allclose(o[0], [200_000.0, 541_000.0, 7_800.0], atol=1.0)


def test_metripose_lahella_origosta_skaalataan_yha(tmp_path):
    """Vanha ehto osui tahan oikein — sen on pysyttava oikein."""
    f = _write(tmp_path / "lahella.e57", _room(1.0), [3.0, 1.5, 1.6])
    o = scanner_origins(f)
    assert np.allclose(o[0], [3_000.0, 1_500.0, 1_600.0], atol=1.0)


def test_millipilven_posea_ei_skaalata(tmp_path):
    """Millipilvi jonka asema on lahella origoa: vanha ehto kertoi 1000:lla.

    Normi on 114 mm eli alle vanhan rajan 200, joten origo lensi metriin.
    """
    f = _write(tmp_path / "millit.e57", _room(1000.0), [100.0, 50.0, 20.0])
    o = scanner_origins(f)
    assert np.allclose(o[0], [100.0, 50.0, 20.0], atol=1.0)


def test_pilvi_ja_origo_samassa_yksikossa(tmp_path):
    """Origon on osuttava pilven omaan laajuuteen — se on koko kentan tarkoitus.

    Ilman tata testi voisi menna lapi vaikka origo olisi eri avaruudessa kuin
    pisteet, ja juuri se oli bugi.
    """
    from scan2bim.core.geometry.loader import load_point_cloud

    f = _write(tmp_path / "yhdessa.e57", _room(1.0), [200.0, 541.0, 7.8])
    pts = np.asarray(load_point_cloud(f).points)
    o = scanner_origins(f)[0]
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    pad = 0.05 * (hi - lo)
    assert np.all(o >= lo - pad) and np.all(o <= hi + pad), (o, lo, hi)


def test_muu_formaatti_ei_anna_origoja(tmp_path):
    p = tmp_path / "x.ply"
    p.write_text("ply\n", encoding="utf-8")
    assert scanner_origins(p) == []

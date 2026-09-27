"""Skannin esitarkastus: varoittaako se ennen ajoa siita mika menee pieleen.

Perjantaina tulee tuntemattomia skanneja koululta. Putki tekee niista useita
oletuksia (mittakaava, lattia/katto, kerrosjako, tiheys) ja jos jokin menee
pieleen, virhe nakyy vasta lopputuloksessa. Nama testit lukitsevat sen etta
varoitus tulee ETUKATEEN.
"""
import numpy as np
import open3d as o3d
import pytest

from ordinate.core.inspect import format_report, inspect_scan

_RNG = np.random.RandomState(3)


def _room_ply(tmp_path, size=6000.0, h=2700.0, step=30.0, scale=1.0, name="s.ply"):
    """Nelja seinaa, lattia ja katto — kirjoitetaan levylle."""
    s = np.arange(0.0, size, step)
    z = np.arange(0.0, h, step)
    ss, zz = np.meshgrid(s, z)
    walls = [
        np.column_stack([ss.ravel(), np.zeros(ss.size), zz.ravel()]),
        np.column_stack([ss.ravel(), np.full(ss.size, size), zz.ravel()]),
        np.column_stack([np.zeros(ss.size), ss.ravel(), zz.ravel()]),
        np.column_stack([np.full(ss.size, size), ss.ravel(), zz.ravel()]),
    ]
    gx, gy = np.meshgrid(s, s)
    slabs = [np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, v)])
             for v in (0.0, h)]
    pts = np.vstack(walls + slabs) * scale
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    p = tmp_path / name
    o3d.io.write_point_cloud(str(p), pc)
    return p


def test_reads_the_levels_the_pipeline_will_use(tmp_path):
    info = inspect_scan(_room_ply(tmp_path))
    assert abs(info["floor_mm"]) < 60.0, info["floor_mm"]
    assert abs(info["ceiling_mm"] - 2700.0) < 60.0, info["ceiling_mm"]
    assert abs(info["room_height_mm"] - 2700.0) < 120.0
    assert len(info["floors"]) == 1
    assert 20.0 < info["spacing_mm"] < 70.0, info["spacing_mm"]


def test_sparse_scan_is_flagged(tmp_path):
    """Harva skanni ei kanna ohutta seinaa — se on sanottava ennen ajoa."""
    info = inspect_scan(_room_ply(tmp_path, step=150.0, name="sparse.ply"))
    assert any("harva" in w for w in info["warnings"]), info["warnings"]


def test_two_storeys_are_reported(tmp_path):
    """Kerrosjako paatetaan ennen mallinnusta; kayttajan on nahtava se."""
    a = np.asarray(o3d.io.read_point_cloud(str(_room_ply(tmp_path))).points)
    b = a.copy()
    b[:, 2] += 3000.0
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack([a, b]))
    p = tmp_path / "two.ply"
    o3d.io.write_point_cloud(str(p), pc)
    info = inspect_scan(p)
    assert len(info["floors"]) == 2, info["floors"]
    assert any("kerrosta" in w for w in info["warnings"]), info["warnings"]


def test_report_is_readable_without_a_bbox(tmp_path):
    """Liian pieni pilvi ei kaada raporttia."""
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(_RNG.uniform(0, 1000, (50, 3)))
    p = tmp_path / "tiny.ply"
    o3d.io.write_point_cloud(str(p), pc)
    info = inspect_scan(p)
    assert info["warnings"]
    assert "50" in format_report(info)


def test_unknown_format_is_refused(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("ei pilvi", encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_scan(p)


def test_density_is_not_inflated_by_sampling(tmp_path):
    """Iso tiedosto luetaan naytteena, mutta tiheys on mitattava yhtenaisesta
    lohkosta — harvennettu naye antaisi liian suuren pistevalin ja vaaran
    'harva skanni' -varoituksen."""
    p = _room_ply(tmp_path, size=9000.0, step=20.0, name="big.ply")
    full = inspect_scan(p, sample=10_000_000)
    part = inspect_scan(p, sample=200_000)
    assert "sampled" in part and "sampled" not in full
    assert abs(part["spacing_mm"] - full["spacing_mm"]) < 8.0, \
        f"naytteistys vaaristi tiheyden: {part['spacing_mm']} vs {full['spacing_mm']}"
    assert not any("harva" in w for w in part["warnings"]), part["warnings"]


def test_working_cloud_size_is_reported(tmp_path):
    """Putki harventaa korkeintaan 25 mm:iin, joten iso rakennus EI kutistu
    kiinteaan pistebudjettiin vaan kasvattaa tyopilvea. Se on nahtava ennen
    ajoa, ei vasta kun ajo hyytyy."""
    info = inspect_scan(_room_ply(tmp_path, step=10.0, name="dense.ply"))
    assert info["work_points"] > 0
    assert info["work_points"] < info["points"], \
        "25 mm voxeli ei harventanut 10 mm skannia"
    assert "työpilvi" in format_report(info)


def test_working_cloud_size_from_a_sample_is_marked_as_a_lower_bound(tmp_path):
    """Naytteesta laskettu luku on ALARAJA — koko pilvi tayttaa vain enemman
    voxeleita. Sita ei saa esittaa tarkkana."""
    p = _room_ply(tmp_path, size=9000.0, step=20.0, name="big2.ply")
    part = inspect_scan(p, sample=50_000)
    assert part["work_exact"] is False
    assert "≥" in format_report(part)
    full = inspect_scan(p, sample=10_000_000)
    assert full["work_exact"] is True
    assert part["work_points"] <= full["work_points"]

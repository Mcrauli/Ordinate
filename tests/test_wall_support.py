"""Tarkistuslista perustuu MITATTUUN pintatukeen, ei detektorin luottamukseen.

Detektorin `confidence` on kokoproxy (contour: 0.80 + pituus/20000), joten
pisin valeseina saa korkeimman luottamuksen. Mitattu Rohbau-GT:lla: 12 aitoa
seinaa peitto 0.29-0.49, 6 valeseinaa 0.016-0.063.
"""
import numpy as np
import open3d as o3d

from scan2bim.core.qa.deviation import flag_low_confidence, measure_wall_support
from scan2bim.schemas.model import ElementSource, StructuralModel, Wall

_H = 2700.0
_T = 200.0


def _wall(wid, x0, y0, x1, y1, conf=1.0):
    return Wall(
        id=wid, confidence=conf, classification="wall",
        source=ElementSource(method="contour"),
        axis=[[x0, y0], [x1, y1]], height=_H, thickness=_T, z_min=0.0,
    )


def _face_points(x0, y0, x1, y1, step=50.0):
    """Molemmat pinnat keilattuna seinalle (x0,y0)-(x1,y1)."""
    a = np.array([x0, y0], float)
    b = np.array([x1, y1], float)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    t = np.arange(0.0, L, step)
    z = np.arange(60.0, _H - 60.0, step)
    tt, zz = np.meshgrid(t, z)
    out = []
    for sgn in (1.0, -1.0):
        xy = a + tt.ravel()[:, None] * u + sgn * (_T / 2.0) * n
        out.append(np.column_stack([xy, zz.ravel()]))
    return np.vstack(out)


def _cloud(arr):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(arr)
    return pcd


def test_scanned_wall_has_support_and_is_not_flagged():
    model = StructuralModel(walls=[_wall("w_real", 0, 0, 6000, 0)])
    measure_wall_support(model, _cloud(_face_points(0, 0, 6000, 0)))
    assert model.walls[0].support is not None
    assert model.walls[0].support > 0.9, model.walls[0].support
    assert flag_low_confidence(model) == []


def test_ghost_wall_without_points_is_flagged():
    """Haamuseina rakennuksen ulkopuolella: taysi luottamus, ei yhtaan pistetta."""
    model = StructuralModel(walls=[
        _wall("w_real", 0, 0, 6000, 0),
        _wall("w_ghost", 0, 4000, 6000, 4000),
    ])
    measure_wall_support(model, _cloud(_face_points(0, 0, 6000, 0)))
    ghost = next(w for w in model.walls if w.id == "w_ghost")
    assert ghost.support == 0.0
    ids = [f["id"] for f in flag_low_confidence(model)]
    assert ids == ["w_ghost"], ids


def test_long_ghost_wall_beats_its_own_confidence():
    """Pisin seina saa contourissa conf=1.0 — pituus ei saa suojata sita."""
    ghost = _wall("w_long_ghost", 0, 9000, 45000, 9000, conf=1.0)
    model = StructuralModel(walls=[_wall("w_real", 0, 0, 6000, 0), ghost])
    measure_wall_support(model, _cloud(_face_points(0, 0, 6000, 0)))
    flags = flag_low_confidence(model)
    assert [f["id"] for f in flags] == ["w_long_ghost"]
    assert flags[0]["confidence"] == 1.0


def test_low_confidence_but_scanned_wall_is_not_flagged():
    """Vanha sääntö liputti taman turhaan (mitattu: apt wall_ext_002, peitto 0.31)."""
    model = StructuralModel(walls=[_wall("w_short", 0, 0, 1800, 0, conf=0.25)])
    measure_wall_support(model, _cloud(_face_points(0, 0, 1800, 0)))
    assert model.walls[0].support > 0.9
    assert flag_low_confidence(model) == []


def _beam_line_points(length=24000.0, step=50.0, bay=8000.0):
    """Palkkilinja: palkki katon alla koko matkalta + pilarit 8 m valein.

    Nain histogrammidetektori tekee 28 m "seinia" Rohbaussa. Pisteita on joka
    korkeudella (palkki ylhaalla, pilarit alhaalla) -> pystytuki on korkea,
    mutta VYOTAROLLA on vain pilarit.
    """
    out = []
    for sgn in (1.0, -1.0):
        y = sgn * _T / 2.0
        # palkki: ylin 20 % korkeudesta, koko pituudelta
        xs = np.arange(0.0, length, step)
        zs = np.arange(_H * 0.80, _H - 30.0, step)
        X, Z = np.meshgrid(xs, zs)
        out.append(np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()]))
        # pilarit: 400 mm leveita, koko korkeudelta
        zs = np.arange(60.0, _H - 60.0, step)
        for x0 in np.arange(0.0, length, bay):
            xs = np.arange(x0, min(x0 + 400.0, length), step)
            if len(xs) == 0:
                continue
            X, Z = np.meshgrid(xs, zs)
            out.append(np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()]))
    return np.vstack(out)


def _long_wall(wid="w_line", length=24000.0, conf=1.0):
    return Wall(
        id=wid, confidence=conf, classification="wall",
        source=ElementSource(method="histogram"),
        axis=[[0.0, 0.0], [length, 0.0]], height=_H, thickness=_T, z_min=0.0,
    )


def test_beam_line_is_flagged_even_though_it_has_support():
    """Palkkilinjalla ON pintatukea — vain jatkuvuus paljastaa sen."""
    model = StructuralModel(walls=[_long_wall()])
    measure_wall_support(model, _cloud(_beam_line_points()))
    w = model.walls[0]
    assert w.support > 0.15, f"tuki {w.support} — testi ei erottele jatkuvuutta"
    assert w.continuity < 0.30, w.continuity
    flags = flag_low_confidence(model)
    assert [f["id"] for f in flags] == ["w_line"]
    assert "yhtenäinen" in flags[0]["reason"]


def test_continuous_long_wall_is_not_flagged():
    model = StructuralModel(walls=[_long_wall("w_solid")])
    measure_wall_support(model, _cloud(_face_points(0, 0, 24000, 0)))
    assert model.walls[0].continuity > 0.9, model.walls[0].continuity
    assert flag_low_confidence(model) == []


def test_doorway_gap_does_not_break_continuity():
    """Oviaukko on reika vyotarolla — se ei saa liputtaa aitoa seinaa."""
    pts = _face_points(0, 0, 6000, 0)
    door = (pts[:, 0] > 2500) & (pts[:, 0] < 3500) & (pts[:, 2] < 2100)
    model = StructuralModel(walls=[_wall("w_door", 0, 0, 6000, 0)])
    measure_wall_support(model, _cloud(pts[~door]))
    assert model.walls[0].continuity >= 0.30, model.walls[0].continuity
    assert flag_low_confidence(model) == []


def test_confidence_still_used_when_support_not_measured():
    model = StructuralModel(walls=[_wall("w_x", 0, 0, 3000, 0, conf=0.25)])
    assert model.walls[0].support is None
    assert [f["id"] for f in flag_low_confidence(model)] == ["w_x"]

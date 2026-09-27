"""Jaannosseinat: detektorin ulkopuolelle jaanyt seina tuodaan ehdokkaaksi.

Mitattu Rohbau3D scene_07000: histogrammi tuottaa nelja seinaa (kaikki 27-30 m)
ja GT:n 49 seinainstanssista mallissa on 24. Jaannoksessa on 15 suoraa
1.2-5.6 m rakennetta joiden GT-luokka on 92-100 % Wall, eli puuttuvat seinat
ovat pilvessa yhtenaisina pintoina - eivat sirontana.
"""
import numpy as np
import open3d as o3d

from ordinate.core.semantics.residual_walls import find_residual_walls
from ordinate.schemas.model import ElementSource, Wall

_H = 3000.0
_RNG = np.random.RandomState(5)


def _wall(wid, x0, y0, x1, y1, th=200.0):
    return Wall(id=wid, confidence=1.0, classification="wall",
                source=ElementSource(method="histogram"),
                axis=[[x0, y0], [x1, y1]], height=_H, thickness=th, z_min=0.0)


def _face(p0, p1, th=200.0, step=25.0, z0=20.0, z1=_H - 20.0):
    """Pystyseinan kaksi pintaa pisteina."""
    a, b = np.array(p0, float), np.array(p1, float)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    s = np.arange(0.0, L, step)
    z = np.arange(z0, z1, step)
    ss, zz = np.meshgrid(s, z)
    out = []
    for sgn in (-1.0, 1.0):
        p = a + np.outer(ss.ravel(), u) + n * sgn * th / 2.0
        out.append(np.column_stack([p, zz.ravel()]))
    return np.vstack(out)


def _cloud(*parts):
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.vstack(parts))
    return pc


def _room(size=20000.0):
    """Perimetri seinina JA pisteina — malli tuntee vain nama."""
    walls = [_wall("w0", 0, 0, size, 0), _wall("w1", size, 0, size, size),
             _wall("w2", size, size, 0, size), _wall("w3", 0, size, 0, 0)]
    pts = [_face((0, 0), (size, 0)), _face((size, 0), (size, size)),
           _face((size, size), (0, size)), _face((0, size), (0, 0))]
    return walls, pts


def test_interior_wall_outside_the_model_is_found():
    """2.5 m valiseina jota histogrammi ei nappaa -> ehdokkaaksi."""
    walls, pts = _room()
    got = find_residual_walls(walls, _cloud(*pts, _face((8000, 6000), (8000, 8500))),
                              floor_z=0.0, ceiling_z=_H)
    assert len(got) == 1, f"jaannosseinia {len(got)}"
    a = np.array(got[0].axis[0])
    b = np.array(got[0].axis[1])
    assert 2000 < np.linalg.norm(b - a) < 3200, f"pituus {np.linalg.norm(b - a):.0f}"
    assert got[0].source.method == "residual"
    # Akseli luetaan pisteista, ei solukeskipisteista: 100 mm solu siirtaisi
    # keskilinjan puoli solua sivuun.
    assert abs(a[0] - 8000.0) < 20.0 and abs(b[0] - 8000.0) < 20.0, f"akseli {a} {b}"
    # Paksuus on MITATTU pintojen valista, ei oletettu.
    assert abs(got[0].thickness - 200.0) < 25.0, f"paksuus {got[0].thickness:.0f}"


def test_wall_already_in_the_model_is_not_duplicated():
    walls, pts = _room()
    seg = _face((8000, 6000), (8000, 10000))
    walls = walls + [_wall("w4", 8000, 6000, 8000, 10000)]
    assert find_residual_walls(walls, _cloud(*pts, seg), floor_z=0.0, ceiling_z=_H) == []


def test_short_stub_is_not_a_wall():
    """Alle metrin pala on pilari tai tolppa, ei seina."""
    walls, pts = _room()
    got = find_residual_walls(walls, _cloud(*pts, _face((8000, 6000), (8000, 6700))),
                              floor_z=0.0, ceiling_z=_H)
    assert got == [], f"tynka tuli seinaksi: {[w.axis for w in got]}"


def test_thin_horizontal_slab_is_not_a_wall():
    """Kalusteen ylapinta on ohut viipale: pystyulottuvuus puuttuu."""
    walls, pts = _room()
    x = np.arange(6000.0, 10000.0, 25.0)
    y = np.arange(6000.0, 6300.0, 25.0)
    xx, yy = np.meshgrid(x, y)
    shelf = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, 1200.0)])
    got = find_residual_walls(walls, _cloud(*pts, shelf), floor_z=0.0, ceiling_z=_H)
    assert got == [], f"hyllytaso tuli seinaksi: {[w.axis for w in got]}"


def test_sparse_scan_finds_the_same_wall():
    """Pintakynnys on suhteellinen, joten harva skanni ei muuta tulosta.

    Absoluuttinen pistemaara per solu sitoisi saannon skannin tiheyteen.
    """
    walls, pts = _room()
    dense = np.vstack([*pts, _face((8000, 6000), (8000, 8500))])
    sparse = dense[::12]
    got = find_residual_walls(walls, _cloud(sparse), floor_z=0.0, ceiling_z=_H)
    assert len(got) == 1, f"harvassa skannissa {len(got)} seinaa"


def test_no_residual_when_the_model_covers_everything():
    walls, pts = _room()
    assert find_residual_walls(walls, _cloud(*pts), floor_z=0.0, ceiling_z=_H) == []


def test_other_face_of_a_known_wall_is_not_a_new_wall():
    """Mallin seinan toinen pinta ei ole uusi seina.

    Mitattu Rohbau scene_07000: ilman tata ehdokkaat sulautuivat
    deduplikoinnissa oikeisiin seiniin ja LYHENSIVAT niita — pistekattavuus
    0.887 -> 0.689 ja 30.3 m seina katkesi 15.4 m:iin.
    """
    walls, pts = _room()
    # Malli tuntee seinan liian ohuena (80 mm) -> sen ulkopinta jaa lunastamatta
    thin = _wall("w4", 8000, 4000, 8000, 12000, th=80.0)
    seg = _face((8000, 4000), (8000, 12000), th=300.0)
    got = find_residual_walls(walls + [thin], _cloud(*pts, seg),
                              floor_z=0.0, ceiling_z=_H)
    assert got == [], f"seinan toinen pinta tuli uudeksi seinaksi: {[w.axis for w in got]}"

"""Tarkistuslista perustuu MITATTUUN pintatukeen, ei detektorin luottamukseen.

Detektorin `confidence` on kokoproxy (contour: 0.80 + pituus/20000), joten
pisin valeseina saa korkeimman luottamuksen. Mitattu Rohbau-GT:lla: 12 aitoa
seinaa peitto 0.29-0.49, 6 valeseinaa 0.016-0.063.
"""
import numpy as np
import open3d as o3d

from ordinate.core.qa.deviation import flag_low_confidence, measure_wall_support
from ordinate.schemas.model import ElementSource, StructuralModel, Wall

_H = 2700.0
_T = 200.0
_PRUNE_CONT_MAX = 0.15


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


def _displaced_face_points(x0, y0, x1, y1, off, step=50.0):
    """Aito seina, mutta mallin akseli on `off` mm sivussa oikeasta pinnasta."""
    pts = _face_points(x0, y0, x1, y1, step=step)
    pts[:, 1] += off
    return pts


def _thin(pts, factor, seed=0):
    rng = np.random.default_rng(seed)
    keep = rng.permutation(len(pts))[: max(1, len(pts) // factor)]
    return pts[keep]


def test_sparse_scan_does_not_turn_a_real_wall_into_a_beam_line():
    """Karsinta ei saa riippua KEILAUSTIHEYDESTA — muuten harva skanni poistaa
    aitoja seinia. Mitattu Rohbaulla: 1/250 harvennus poisti kaksi GT-aitoa
    seinaa, ja synteettisesti erottelu (aito - palkki) romahti 0.94 -> 0.00.
    """
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    sparse = _thin(_face_points(0, 0, 24000, 0), 250)
    model = StructuralModel(walls=[_long_wall("w_sparse")])
    measure_wall_support(model, _cloud(sparse))
    # ennen: 0.0 (= palkkilinja, poisto). Raja 0.30 on liputuskynnys.
    assert model.walls[0].continuity >= 0.30, model.walls[0].continuity
    assert prune_unsupported_walls(model, _cloud(sparse)) == []


def test_beam_line_is_still_caught_when_the_scan_is_sparse():
    """Erottelun on sailyttava molempiin suuntiin, ei vain 'ala poista'."""
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    model = StructuralModel(walls=[_long_wall("w_line")])
    measure_wall_support(model, _cloud(_thin(_beam_line_points(), 50)))
    assert model.walls[0].continuity < _PRUNE_CONT_MAX, model.walls[0].continuity
    assert prune_unsupported_walls(model) == ["w_line"]


def test_short_wall_is_never_pruned_because_it_cannot_prove_a_beam_line():
    """Sama syy kuin napsautuksessa: 1.0 m seinassa on kaksi saraketta, joten
    jatkuvuus ei todista kumpaankaan suuntaan. Palkkilinjat ovat aina pitkia
    (Rohbaussa 28 m) — lyhyiden suojaaminen ei siis maksa mitaan.
    """
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    sparse = _thin(_face_points(0, 0, 1000, 0), 100)
    model = StructuralModel(walls=[_wall("w_tiny", 0, 0, 1000, 0)])
    measure_wall_support(model, _cloud(sparse))
    assert prune_unsupported_walls(model, _cloud(sparse)) == []


def test_short_phantom_is_still_pruned_when_the_place_is_truly_empty():
    """Suoja ei saa pelastaa Rohbaun 3.0 m ja 2.0 m perimetrihaamuja: niiden
    ymparilla on 0 pistetta ±1 m vyotarolla JOKA tiheydella, kun aidoilla
    lyhyilla on 63 754 / 46 581 taydella pilvella ja yha 36 / 27 kun pilvi on
    harvennettu 1/2500:aan. Ero on tyhja vs ei-tyhja, ei tiheyskynnys.
    """
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    real = _face_points(0, 0, 6000, 0)
    model = StructuralModel(walls=[
        _wall("w_real", 0, 0, 6000, 0),
        _wall("w_stub", 0, 30000, 2000, 30000),      # kaukana, ei mitaan ymparilla
    ])
    measure_wall_support(model, _cloud(real))
    assert prune_unsupported_walls(model, _cloud(real)) == ["w_stub"]


def test_beam_line_is_pruned_from_the_model():
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    model = StructuralModel(walls=[_long_wall("w_line"), _wall("w_real", 0, 9000, 6000, 9000)])
    pts = np.vstack([_beam_line_points(), _face_points(0, 9000, 6000, 9000)])
    measure_wall_support(model, _cloud(pts))
    assert prune_unsupported_walls(model) == ["w_line"]
    assert [w.id for w in model.walls] == ["w_real"]


def test_displaced_real_wall_is_kept_for_review_not_pruned():
    """Kauppakeskuksen wall_ext_010: aito GT-seina 375 mm sivussa — EI saa poistua."""
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    model = StructuralModel(walls=[_wall("w_moved", 0, 0, 6000, 0)])
    measure_wall_support(model, _cloud(_displaced_face_points(0, 0, 6000, 0, 500.0)))
    w = model.walls[0]
    assert w.support_offset is not None and w.support_offset >= 250.0, w.support_offset
    assert prune_unsupported_walls(model) == []
    assert [f["id"] for f in flag_low_confidence(model)] == ["w_moved"]


def _clutter_blob(x0, y, n=4000, seed=0):
    """Tavarakasa seinan vieressa: paljon pisteita, mutta vain metrin matkalla."""
    rng = np.random.default_rng(seed)
    return np.column_stack([
        rng.uniform(x0, x0 + 1000.0, n),
        rng.normal(y, 25.0, n),
        rng.uniform(200.0, _H - 200.0, n),
    ])


def test_phantom_next_to_clutter_is_pruned_not_saved_by_its_offset():
    """Mitattu Rohbau: wall_ext_001/007 saivat offsetin 442/825 mm PELKASTA
    kohinasta, joten siirtymaraja suojeli haamua. Vastineen pitaa olla
    jatkuva pinta, ei mika tahansa histogrammihuippu.
    """
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    model = StructuralModel(walls=[_long_wall("w_phantom")])
    cloud = _cloud(_clutter_blob(3000.0, 400.0))
    measure_wall_support(model, cloud)
    w = model.walls[0]
    assert w.support == 0.0 and w.continuity < _PRUNE_CONT_MAX, (w.support, w.continuity)
    assert w.support_offset is None, f"kohinahuippu raportoitiin pintana: {w.support_offset}"
    assert prune_unsupported_walls(model) == ["w_phantom"]


def test_pruning_takes_the_openings_with_it():
    """Muuten IFC:hen jaisi aukko jonka seinaa ei ole."""
    from ordinate.schemas.model import Opening
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    model = StructuralModel(
        walls=[_long_wall("w_line")],
        openings=[Opening(id="op_0", confidence=0.9, source=ElementSource(method="opening"),
                          opening_type="door", wall_id="w_line", position_along=1000.0,
                          width=900.0, sill_height=0.0, opening_height=2100.0)],
    )
    measure_wall_support(model, _cloud(_beam_line_points()))
    assert prune_unsupported_walls(model) == ["w_line"]
    assert model.openings == []


def test_good_model_is_untouched_by_pruning():
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    model = StructuralModel(walls=[_wall("w_a", 0, 0, 6000, 0), _wall("w_b", 0, 4000, 6000, 4000)])
    pts = np.vstack([_face_points(0, 0, 6000, 0), _face_points(0, 4000, 6000, 4000)])
    measure_wall_support(model, _cloud(pts))
    assert prune_unsupported_walls(model) == []
    assert len(model.walls) == 2


def _snap(model, cloud):
    from ordinate.core.semantics.wall_semantics import snap_displaced_walls
    return snap_displaced_walls(model, cloud)


def _one_sided_points(x0, y0, x1, y1, face_y, step=50.0):
    """Yksipuolinen ulkoseina: VAIN sisapinta keilattu (kuten oikeassa datassa)."""
    a = np.array([x0, y0], float)
    b = np.array([x1, y1], float)
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    n = np.array([-u[1], u[0]])
    t = np.arange(0.0, L, step)
    z = np.arange(60.0, _H - 60.0, step)
    tt, zz = np.meshgrid(t, z)
    xy = a + tt.ravel()[:, None] * u + face_y * n
    return np.column_stack([xy, zz.ravel()])


def test_displaced_one_sided_wall_is_snapped_onto_its_surface():
    """Kauppakeskuksen 99.8 m ULKOseina oli 417 mm sivussa -> 29 mm.

    Yksipuolinen: vain sisapinta on keilattu, joten mallin pinta kuuluu sille.
    """
    face = 500.0                      # keilattu pinta 500 mm mallin akselista
    model = StructuralModel(walls=[_wall("w_moved", 0, 0, 12000, 0)])
    cloud = _cloud(_one_sided_points(0, 0, 12000, 0, face))
    measure_wall_support(model, cloud)
    assert model.walls[0].support == 0.0
    moved = _snap(model, cloud)
    assert len(moved) == 1 and moved[0][0] == "w_moved"
    # akselin pitaa siirtya niin etta PINTA (akseli + t/2) osuu keilatulle tasolle
    y = model.walls[0].axis[0][1]
    assert abs((y + _T / 2.0) - face) < 60.0, f"pinta {y + _T/2.0}, odotettu ~{face}"
    measure_wall_support(model, cloud)
    assert model.walls[0].support > 0.9
    assert flag_low_confidence(model) == []


def test_two_sided_displaced_wall_improves_but_lands_within_half_a_thickness():
    """TUNNETTU RAJOITUS: napsautus kohdistaa YHDEN pinnan, ei kahden keskikohtaa.

    Kaksipuolisella siirtyneella seinalla jaannos on enintaan puoli paksuutta —
    yha selvasti parempi kuin satojen millien virhe, mutta ei nolla. Oikea
    mitattu tapaus (yksipuolinen ulkoseina) osuu tarkasti.
    """
    off = 500.0
    model = StructuralModel(walls=[_wall("w_two", 0, 0, 12000, 0)])
    cloud = _cloud(_displaced_face_points(0, 0, 12000, 0, off))
    measure_wall_support(model, cloud)
    assert _snap(model, cloud)
    err = abs(model.walls[0].axis[0][1] - off)
    assert err <= _T / 2.0 + 15.0, err
    assert err < off / 2.0, "siirto ei parantanut riittavasti"


def test_partly_supported_wall_is_still_snapped_onto_its_real_surface():
    """Mitattu aulassa: `wall_007` tuki 0.17 mutta oikea pinta 842 mm sivussa.

    Vanha ehto `support == 0` ohitti sen, koska mallin pinnalla sattui olemaan
    hajapisteita. Siirtyneisyys ei katoa siita etta seinaa raapaisee jokin.
    """
    off = 500.0
    model = StructuralModel(walls=[_wall("w_part", 0, 0, 12000, 0)])
    scatter = _face_points(0, 0, 12000, 0, step=400.0)      # harva raapaisu mallin pinnalla
    real = _one_sided_points(0, 0, 12000, 0, off, step=40.0)  # tiheä oikea pinta
    cloud = _cloud(np.vstack([scatter, real]))
    measure_wall_support(model, cloud)
    w = model.walls[0]
    assert 0.0 < w.support < 0.50, w.support
    moved = _snap(model, cloud)
    assert [i for i, _ in moved] == ["w_part"], moved
    assert abs((model.walls[0].axis[0][1] + _T / 2.0) - off) < 60.0


def test_well_supported_wall_is_not_snapped_even_if_something_lies_beside_it():
    """Yli puoliksi keilattu pinta on jo oikeassa paikassa — sita ei sarjeta."""
    model = StructuralModel(walls=[_wall("w_ok", 0, 0, 12000, 0)])
    cloud = _cloud(np.vstack([_face_points(0, 0, 12000, 0),
                              _one_sided_points(0, 0, 12000, 0, 600.0, step=40.0)]))
    measure_wall_support(model, cloud)
    assert model.walls[0].support >= 0.50, model.walls[0].support
    before = [list(p) for p in model.walls[0].axis]
    assert _snap(model, cloud) == []
    assert [list(p) for p in model.walls[0].axis] == before


def test_short_wall_is_never_snapped_because_it_cannot_prove_a_counterpart():
    """Rohbaun GT-aito `wall_ext_011` (1.0 m) hyppasi 400 mm ja tuki putosi
    0.212 -> 0.155: 500 mm sarakkeilla lyhyeen seinaan mahtuu kaksi saraketta,
    joten jatkuvuusehto 0.80 tayttyy milla tahansa laiskalla. Kattavuus 0.792
    -> 0.749 ja tarkkuus 0.918 -> 0.905 Rohbau-GT:lla.
    """
    model = StructuralModel(walls=[_wall("w_short", 0, 0, 1000, 0)])
    blob = _clutter_blob(0.0, 400.0, n=3000, seed=1)
    blob = blob[blob[:, 0] < 1000.0]
    cloud = _cloud(blob)
    measure_wall_support(model, cloud)
    before = [list(p) for p in model.walls[0].axis]
    assert _snap(model, cloud) == []
    assert [list(p) for p in model.walls[0].axis] == before


def test_phantom_without_a_counterpart_is_not_snapped():
    """Rohbaun perimetritynka: ei vastinetta -> ei saa siirtaa mihinkaan."""
    model = StructuralModel(walls=[
        _wall("w_real", 0, 0, 6000, 0),
        _wall("w_ghost", 0, 9000, 6000, 9000),
    ])
    cloud = _cloud(_face_points(0, 0, 6000, 0))
    measure_wall_support(model, cloud)
    assert _snap(model, cloud) == []


def test_fragment_counterpart_does_not_drag_the_wall():
    """Lyhyt sirpale ei ole seina — jatkuvuusehto estaa siirron."""
    pts = _displaced_face_points(0, 0, 12000, 0, 500.0)
    frag = pts[pts[:, 0] < 2000.0]           # vain 17 % pituudesta
    model = StructuralModel(walls=[_wall("w_frag", 0, 0, 12000, 0)])
    cloud = _cloud(frag)
    measure_wall_support(model, cloud)
    assert _snap(model, cloud) == []


def test_supported_wall_is_never_moved():
    model = StructuralModel(walls=[_wall("w_ok", 0, 0, 6000, 0)])
    cloud = _cloud(_face_points(0, 0, 6000, 0))
    measure_wall_support(model, cloud)
    before = [list(p) for p in model.walls[0].axis]
    assert _snap(model, cloud) == []
    assert [list(p) for p in model.walls[0].axis] == before


def test_confidence_still_used_when_support_not_measured():
    model = StructuralModel(walls=[_wall("w_x", 0, 0, 3000, 0, conf=0.25)])
    assert model.walls[0].support is None
    assert [f["id"] for f in flag_low_confidence(model)] == ["w_x"]


def _sparse_face(x0, y0, x1, y1, keep=400):
    """Pinta josta on niin vahan pisteita ettei jatkuvuutta voi vaittaa."""
    q = _face_points(x0, y0, x1, y1)
    return q[:: max(len(q) // keep, 1)]


def _floor_clutter_face(x0, y0, x1, y1, z_hi=700.0, step=50.0):
    """Pintaa vain lattian tuntumassa: vyotarolla ei ole yhtaan pistetta.

    Nain jatkuvuus jaa mittaamatta (`_CONT_MIN_WAIST`) vaikka tuki mitataan —
    juuri Rohbaun wall_ext_002:n tilanne.
    """
    q = _face_points(x0, y0, x1, y1, step=step)
    return q[q[:, 2] < z_hi]


def test_wall_whose_continuity_could_not_be_measured_is_not_taken_as_proven():
    """Mittaamattomuus ei ole todiste tuesta.

    Jatkuvuus jaa mittaamatta juuri silloin kun vyotarolla ei ole pisteita
    (`_CONT_MIN_WAIST`), joten seina jolla on VAHITEN evidenssia paasi
    portista lapi. Mitattu Rohbau: wall_ext_002 sup=0.022 cont=None
    (scene_07001) ja sup=0.034 cont=None (scene_07003) jaivat malliin, ja QA
    merkitsi molemmat vaaran luokan seiniksi. Aitojen seinien tuki samoissa
    malleissa on 0.329-0.923.
    """
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    real = _face_points(0, 0, 6000, 0)
    clutter = _floor_clutter_face(0, 9000, 6000, 9000)
    model = StructuralModel(walls=[
        _wall("w_real", 0, 0, 6000, 0),
        _wall("w_ghost", 0, 9000, 6000, 9000),   # 6 m perimetrihaamu lattiaroinan paalla
    ])
    pts = np.vstack([real, clutter])
    measure_wall_support(model, _cloud(pts))
    ghost = next(w for w in model.walls if w.id == "w_ghost")
    assert ghost.continuity is None, f"jatkuvuus {ghost.continuity} — fikstuuri ei osu"
    assert prune_unsupported_walls(model, _cloud(pts)) == ["w_ghost"]


def test_measured_support_still_saves_a_wall_without_continuity():
    """Jos tuki on MITATTU ja hyva, jatkuvuuden puuttuminen ei saa poistaa seinaa."""
    from ordinate.core.semantics.wall_semantics import prune_unsupported_walls
    pts = _face_points(0, 0, 6000, 0)
    model = StructuralModel(walls=[_wall("w_real", 0, 0, 6000, 0)])
    measure_wall_support(model, _cloud(pts))
    w = model.walls[0]
    assert w.support is not None and w.support >= 0.15, w.support
    assert prune_unsupported_walls(model, _cloud(pts)) == []

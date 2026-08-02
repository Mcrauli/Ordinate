"""Pilaridetektio: pystysuuntaiset, seinistä irralliset pistekasaumat.

Algoritmi:
  1. Poista seinien lähipisteet (jää vapaasti seisovat rakenteet)
  2. Rajaa keskikorkeuden kaistaan (pois lattia/katto)
  3. DBSCAN-klusterointi XY:ssä
  4. Klusteri = pilari jos pieni XY-jalanjälki + ulottuu lähes lattiasta kattoon
"""
from __future__ import annotations

import numpy as np
import open3d as o3d

from scan2bim.schemas.model import Column, ColumnProfile, ElementSource, Wall

_WALL_MARGIN = 120.0       # mm — tätä lähempänä seinää = seinäpiste, ohitetaan
_Z_MARGIN = 300.0          # mm — lattia/katto-vyöhyke pois
_MAX_FOOTPRINT = 700.0     # mm — pilarin max XY-mitta
_MIN_FOOTPRINT = 80.0      # mm
_MIN_HEIGHT_FRAC = 0.55    # ulotuttava vähintään tämä osuus huonekorkeudesta
_DBSCAN_EPS = 150.0        # mm
_DBSCAN_MIN_PTS = 40
_MIN_CLUSTER_PTS = 120


_CELL_MM = 100.0           # XY-ruudukon solu
_ZBIN_MM = 200.0           # pystypeiton binikoko
_VFILL_MIN = 0.70          # solun pystytäyttö ≥ tämä → pilariehdokas
_COMP_MIN_MM = 180.0       # komponentin min-mitta (holvituki ~70mm putoaa)
_COMP_MAX_MM = 800.0       # komponentin max-mitta
_RING_IN = 2               # rengas alkaa (soluja bboxin reunasta)
_RING_OUT = 6              # rengas päättyy
_RING_MAX_CELLS = 6        # renkaassa saa olla korkeintaan näin monta täyttösolua
_MIN_ABS_HEIGHT = 2300.0   # mm — monitasoscenessä room_h vääristyy; aito pilari ≥ tämä
_MAX_ASPECT = 2.5          # footprintin max/min — yli tämän = seinänpala, ei pilari
                           # (mitattu: Rohbau-työmaan aidot pilarit 1.1–2.3)

# Poikkileikkauksen VAKAUS korkeussuunnassa: aidon pilarin XY-jalanjälki on ~sama
# joka korkeudella. Kasattu kaluste / keilausvarjon reuna heiluu (mitattu 3DSES-
# huoneesta: valepilari 35↔500 mm eri korkeuksilla). Leikataan klusteri z-kaistoihin
# ja vaadittava että enemmistön poikkileikkaus on lähellä mediaania.
_SLICE_MM = 250.0          # z-kaistan paksuus
_SLICE_MIN_PTS = 30        # kaista huomioidaan vasta tällä pistemäärällä
_SLICE_MIN_BINS = 4        # vähintään näin monta kelvollista kaistaa (~1 m yhtenäistä)
_SLICE_CONSIST_FRAC = 0.6  # kelvollisista kaistoista tämä osuus lähellä mediaania
_SLICE_LO, _SLICE_HI = 0.5, 1.7   # "lähellä" = poikkileikkaus tällä välillä × mediaani

# Keskikorkeuden IRRALLISUUS = VAPAA KAARI: aidon pilarin OHI PÄÄSEE KÄVELEMÄÄN.
# Renkaassa juuri footprintin ulkopuolella, vain vyötärökaistan pisteillä (ei
# lattia/katto): kuinka leveä on suurin YHTENÄINEN vapaa kulmasektori.
#
# Tässä luettiin ennen sektorien MÄÄRÄÄ (raja 4). Se on väärä mittari, ja
# liiketilassa se hylkäsi aidot pilarit: myymälässä gondoli seisoo pilarin
# molemmin puolin, jolloin aito pilari peittää 12–16 sektoria — täsmälleen yhtä
# monta kuin hylättävä tavaran ympäröimä kaappi (16). Määrä ei siis erottele
# lainkaan. KAARI erottelee, koska tavara joka suunnassa ei jätä kulkuaukkoa:
#   mitattu, myymälän 34 GT-pilaria : 60° (10 kpl, käytävä) tai 360° (24 kpl)
#   mitattu, tavaran ympäröimä kaappi: 30°   (testin 3DSES-tapaus c1/c2)
# Raja 45° erottaa molemmat yhden sektorin marginaalilla.
_WAIST_LO, _WAIST_HI = 1000.0, 1800.0   # vyötärökaista lattiasta (mm)
_SECTOR_N = 24             # kulmasektoreiden määrä
_SECTOR_RING_IN = 150.0    # renkaan alku footprintin reunasta (mm) — yli neliön
                           # kulman (0.71×leveys) jottei pilarin omat kulmat laske
_SECTOR_RING_OUT = 700.0   # renkaan loppu
_MIN_FREE_ARC_DEG = 45.0   # alle tämän leveä suurin vapaa kaari = ympäröity → hylky
_MIN_REAL_FOOTPRINT = 200.0  # alle tämän leveä = ohut donitsi/artefakti, ei aito pilari
                             # (mitattu S170: valepilarit 147/195 mm; aidot Rohbau ≥240)

# Irtiolo SEINÄSTÄ. Moduulin määritelmä on "seinistä irralliset kasaumat", mutta
# _WALL_MARGIN karsii vain PISTEITÄ: seinän mutka tai paksunnos, jota seinä-
# detektori ei napannut, jää omaksi kasaumakseen ja täyttää kaikki muut ehdot.
# Kuvista varmistettu (data/_col_view.py, asunto apt2): kaikki kolme ehdokasta
# istuivat seinälinjalla — mutkassa, seinän päässä ja seinäsegmentin kohdalla.
# Mitattu vapaa väli ehdokkaan reunasta seinäpintaan:
#   asunnon valeet          : -123, -40, +104 mm  (kaksi seinän SISÄLLÄ)
#   myymälän aidot pilarit  : 5420 mm ja yli
# Aito vapaa pilari seisoo irti seinästä; seinään kiinni oleva on pilasteri ja
# kuuluu seinään.
_MIN_WALL_CLEARANCE = 250.0  # mm — ehdokkaan reunasta seinäpintaan


def detect_columns(cloud, walls: list[Wall], floor_z: float, ceiling_z: float) -> list[Column]:
    """Pystypeittopohjainen pilaridetektio.

    DBSCAN-klusterointi HYLÄTTY: työmaalla holvituet/tavara ketjuttavat
    pilarin naapurikramaan (eps-ketju) → jättiklusteri → footprint-hylky →
    0/92 GT-pilaria. Pilarin tuntomerkki ei ole irrallisuus vaan PYSTYPEITTO:
    XY-solu jonka z-binit ovat täynnä lattiasta kattoon. Ohut holvituki
    täyttää pystysuunnan mutta on ≤120mm → komponentin minimimitta hylkää."""
    from scipy.ndimage import label as _cc_label

    pts = np.asarray(cloud.points)
    if len(pts) < _MIN_CLUSTER_PTS:
        return []
    room_h = ceiling_z - floor_z
    if room_h < 1500.0:
        return []

    zmask = (pts[:, 2] > floor_z + _Z_MARGIN) & (pts[:, 2] < ceiling_z - _Z_MARGIN)
    band = pts[zmask]
    if len(band) < _MIN_CLUSTER_PTS:
        return []
    far = _dist_to_walls(band[:, :2], walls) > _WALL_MARGIN
    free = band[far]
    if len(free) < _MIN_CLUSTER_PTS:
        return []

    # Ympäröintitesti: aito pilari seisoo KEILATUN tilan sisällä (dataa joka
    # suuntaan). Keilausvarjon/skannireunan artefakti (hajonnut skanni) on
    # datan REUNALLA → ulkopuoli on tyhjä. Näyte 8 suuntaan 1000mm renkaalla:
    # jos <5 suunnassa on pisteitä ≤600mm päässä, pilari on reunalla → hylky.
    from scipy.spatial import cKDTree
    _xytree = cKDTree(pts[::4, :2]) if len(pts) > 4000 else None
    _RING_R, _RING_TOL, _RING_HITS = 1000.0, 600.0, 5
    _ang = np.linspace(0.0, 2 * np.pi, 8, endpoint=False)
    _cos, _sin = np.cos(_ang), np.sin(_ang)

    def _surrounded(cx: float, cy: float) -> bool:
        if _xytree is None:
            return True
        probes = np.column_stack([cx + _RING_R * _cos, cy + _RING_R * _sin])
        d, _ = _xytree.query(probes, k=1)
        return int((d < _RING_TOL).sum()) >= _RING_HITS

    # vyötärökaistan (1.0–1.8 m) pisteet irrallisuustestiin — vain jos kaista mahtuu
    _waist_mask = (pts[:, 2] > floor_z + _WAIST_LO) & (pts[:, 2] < floor_z + _WAIST_HI)
    _waist_pts = pts[_waist_mask, :2] if int(_waist_mask.sum()) > 200 else None
    _waist_tree = cKDTree(_waist_pts) if _waist_pts is not None else None

    x0 = float(free[:, 0].min()); y0 = float(free[:, 1].min())
    ix = ((free[:, 0] - x0) / _CELL_MM).astype(np.int64)
    iy = ((free[:, 1] - y0) / _CELL_MM).astype(np.int64)
    z_lo = floor_z + _Z_MARGIN
    iz = ((free[:, 2] - z_lo) / _ZBIN_MM).astype(np.int64)
    nx, ny = int(ix.max()) + 1, int(iy.max()) + 1
    nz = max(int((ceiling_z - _Z_MARGIN - z_lo) / _ZBIN_MM), 1)
    iz = np.clip(iz, 0, nz - 1)

    # per-solu pystytäyttö: montako eri z-biniä on ≥2 pistettä
    flat = (ix * ny + iy) * nz + iz
    counts = np.bincount(flat, minlength=nx * ny * nz).reshape(nx, ny, nz)
    vfill = (counts >= 2).sum(axis=2) / nz
    cand = vfill >= _VFILL_MIN

    labels, ncomp = _cc_label(cand, structure=np.ones((3, 3), dtype=int))
    columns: list[Column] = []
    for k in range(1, ncomp + 1):
        cells_x, cells_y = np.nonzero(labels == k)
        ext_x = (cells_x.max() - cells_x.min() + 1) * _CELL_MM
        ext_y = (cells_y.max() - cells_y.min() + 1) * _CELL_MM
        if not (_COMP_MIN_MM <= max(ext_x, ext_y) <= _COMP_MAX_MM):
            continue
        # Rengastesti: aito pilari on IRRALLAAN — detektoimatta jääneen seinän
        # pala on pystytäytöltään pilarin näköinen, mutta sen LINJASSA on lisää
        # täyttösoluja. Jos renkaassa (2..6 solua bboxista) on muiden
        # komponenttien kandidaattisoluja, kyse on seinästä/hyllystä.
        rx0 = max(cells_x.min() - _RING_OUT, 0); rx1 = min(cells_x.max() + _RING_OUT + 1, nx)
        ry0 = max(cells_y.min() - _RING_OUT, 0); ry1 = min(cells_y.max() + _RING_OUT + 1, ny)
        ring = cand[rx0:rx1, ry0:ry1].copy()
        ix0 = max(cells_x.min() - _RING_IN, 0); ix1 = min(cells_x.max() + _RING_IN + 1, nx)
        iy0 = max(cells_y.min() - _RING_IN, 0); iy1 = min(cells_y.max() + _RING_IN + 1, ny)
        ring[ix0 - rx0:ix1 - rx0, iy0 - ry0:iy1 - ry0] = False
        if int(ring.sum()) >= _RING_MAX_CELLS:
            continue
        # pisteet komponentin soluista (+1 solun marginaali profiilia varten)
        in_comp = (
            (ix >= cells_x.min() - 1) & (ix <= cells_x.max() + 1)
            & (iy >= cells_y.min() - 1) & (iy <= cells_y.max() + 1)
        )
        cl = free[in_comp]
        if len(cl) < _MIN_CLUSTER_PTS:
            continue
        z_extent = float(cl[:, 2].max() - cl[:, 2].min())
        if z_extent < min(_MIN_HEIGHT_FRAC * room_h, _MIN_ABS_HEIGHT):
            continue
        xy = cl[:, :2]
        wx = float(np.percentile(xy[:, 0], 98) - np.percentile(xy[:, 0], 2))
        wy = float(np.percentile(xy[:, 1], 98) - np.percentile(xy[:, 1], 2))
        if not (_MIN_FOOTPRINT <= max(wx, wy) <= _MAX_FOOTPRINT):
            continue
        # Ohut footprint = donitsi/artefakti, ei aito pilari (S170 valepilarit 147/195 mm).
        if max(wx, wy) < _MIN_REAL_FOOTPRINT:
            continue
        # Muotosuhde: aito pilari on kompakti (mitattu Rohbau-työmaa: 1.1–2.3).
        # Pitkänomaiset (>_MAX_ASPECT) ovat detektoimattomia seinänpaloja tai
        # keilausvarjon reunoja — juuri se "sälä" kalustetuissa/sotkuisissa tiloissa.
        aspect = max(wx, wy) / max(min(wx, wy), 1.0)
        if aspect > _MAX_ASPECT:
            continue
        cx = float(xy[:, 0].mean()); cy = float(xy[:, 1].mean())
        # Irti seinästä? Tarkistetaan ennen kalliita testejä.
        if walls:
            clear = float(_dist_to_walls(np.array([[cx, cy]]), walls)[0]) - max(wx, wy) / 2.0
            if clear < _MIN_WALL_CLEARANCE:
                continue
        if not _surrounded(cx, cy):
            continue
        # Poikkileikkauksen vakaus: kasattu kaluste heiluu, aito pilari ei.
        if not _cross_section_stable(cl, floor_z, ceiling_z):
            continue
        # Vyötärö-sektoripeitto: seinänpätkä/donitsi/kaappi on kiinni massassa.
        if not _waist_isolated(cx, cy, max(wx, wy), _waist_pts, _waist_tree):
            continue
        shape, w, d = _profile(xy, cx, cy, wx, wy)
        # Luottamus heijastaa kompaktiutta (ei enää satu 1.0:aan): kompakti +
        # tiheä = korkea; pitkänomainen = matala → QA:n TARKISTA-lista poimii sen.
        _compact = max(0.0, min(1.0, (_MAX_ASPECT - aspect) / (_MAX_ASPECT - 1.0)))
        _conf = round(min(1.0, len(cl) / 600.0) * (0.4 + 0.6 * _compact), 3)
        columns.append(Column(
            id=f"column_{len(columns):03d}",
            confidence=_conf,
            classification="column",
            source=ElementSource(method="cluster", notes="vertical-fill"),
            location=[round(cx, 1), round(cy, 1)],
            base_z=round(floor_z, 1),
            height=round(min(z_extent + 2 * _Z_MARGIN, room_h), 1),
            profile=ColumnProfile(shape=shape, width=round(w, 1), depth=round(d, 1)),
        ))
    return columns


def _cross_section_stable(cl: np.ndarray, floor_z: float, ceiling_z: float) -> bool:
    """Aidon pilarin XY-poikkileikkaus on ~sama joka korkeudella. Leikataan
    z-kaistoihin ja katsotaan onko enemmistön poikkileikkaus lähellä mediaania."""
    z_lo = floor_z + _Z_MARGIN
    z_hi = ceiling_z - _Z_MARGIN
    exts: list[float] = []
    z = z_lo
    while z < z_hi:
        m = (cl[:, 2] >= z) & (cl[:, 2] < z + _SLICE_MM)
        if int(m.sum()) >= _SLICE_MIN_PTS:
            b = cl[m]
            ex = float(np.percentile(b[:, 0], 95) - np.percentile(b[:, 0], 5))
            ey = float(np.percentile(b[:, 1], 95) - np.percentile(b[:, 1], 5))
            exts.append(max(ex, ey))
        z += _SLICE_MM
    if len(exts) < _SLICE_MIN_BINS:
        return False
    med = float(np.median(exts))
    if med < 1.0:
        return False
    consistent = sum(1 for e in exts if _SLICE_LO * med <= e <= _SLICE_HI * med)
    return consistent / len(exts) >= _SLICE_CONSIST_FRAC


def _waist_isolated(cx: float, cy: float, fp: float, waist_pts, waist_tree) -> bool:
    """Aito pilari on irrallaan: vyötärökorkeudella sen ohi pääsee kävelemään.

    Renkaassa footprintin ulkopuolella katsotaan mikä on suurin YHTENÄINEN
    vapaa kulmasektori. Vapaana seisova pilari 360°, käytävällä gondolien
    välissä 60°, tavaran joka suunnasta ympäröimä kaappi 30° (kaikki mitattu).
    Sektorien MÄÄRÄ ei erottele näitä — kaari erottelee."""
    if waist_tree is None or waist_pts is None:
        return True
    r_out = fp / 2.0 + _SECTOR_RING_OUT
    idx = waist_tree.query_ball_point([cx, cy], r_out)
    if not idx:
        return True
    rel = waist_pts[idx] - np.array([cx, cy])
    d = np.hypot(rel[:, 0], rel[:, 1])
    band = (d >= fp / 2.0 + _SECTOR_RING_IN) & (d <= r_out)
    if not band.any():
        return True
    ang = np.arctan2(rel[band, 1], rel[band, 0]) % (2 * np.pi)
    sec = (ang / (2 * np.pi) * _SECTOR_N).astype(int) % _SECTOR_N
    occupied = np.zeros(_SECTOR_N, dtype=bool)
    occupied[np.unique(sec)] = True
    if not occupied.any():
        return True
    # pisin vapaa jakso ympyrällä: kierretään kehä kahdesti, katkaistaan _SECTOR_N:ään
    best = run = 0
    for i in range(2 * _SECTOR_N):
        if occupied[i % _SECTOR_N]:
            run = 0
        else:
            run += 1
            best = max(best, min(run, _SECTOR_N))
    return best * 360.0 / _SECTOR_N >= _MIN_FREE_ARC_DEG


def _profile(xy: np.ndarray, cx: float, cy: float, wx: float, wy: float):
    """Pyöreä jos pisteet ovat tasaisella säteellä, muuten suorakaide."""
    r = np.hypot(xy[:, 0] - cx, xy[:, 1] - cy)
    r_mean = float(r.mean())
    if r_mean > 1e-6 and float(r.std()) / r_mean < 0.20 and abs(wx - wy) < 0.3 * max(wx, wy):
        diam = 2.0 * r_mean
        return "circle", diam, diam
    return "rect", wx, wy


def _dist_to_walls(xy: np.ndarray, walls: list[Wall]) -> np.ndarray:
    """Pisteiden min-etäisyys seinäpintaan XY:ssä (akseli miinus puolipaksuus)."""
    if not walls:
        return np.full(len(xy), np.inf)
    dmin = np.full(len(xy), np.inf)
    for w in walls:
        if len(w.axis) < 2:
            continue
        p0 = np.array(w.axis[0], dtype=float)
        p1 = np.array(w.axis[1], dtype=float)
        seg = p1 - p0
        L2 = float(seg @ seg)
        if L2 < 1.0:
            continue
        t = np.clip(((xy - p0) @ seg) / L2, 0.0, 1.0)
        proj = p0[None, :] + t[:, None] * seg[None, :]
        d = np.linalg.norm(xy - proj, axis=1) - w.thickness / 2.0
        dmin = np.minimum(dmin, d)
    return dmin

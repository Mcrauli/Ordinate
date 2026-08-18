"""
Pipeline-orkestroija. Ajaa kaikki vaiheet järjestyksessä ja palauttaa StructuralModel.
Kutsu: model = Pipeline(config).run(input_path, output_dir)
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from scan2bim.schemas.model import StructuralModel, Metadata

log = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    voxel_size: float = 12.0                                   # mm (manuaalinen, kun auto_voxel=False)
    auto_voxel: bool = True            # valitse voxelikoko datasta automaattisesti
    detector: Literal["ransac", "density", "floorplan", "normals", "contour", "histogram"] = "contour"
    export_ifc: bool = True
    export_dxf: bool = True
    export_qa: bool = True                                     # QA/LOA-poikkeamaraportti
    qa_tolerance: float = 2.5                                  # mm
    icp_refine: bool = False                                   # ICP-hienorekisteröinti monoskannauksille
    save_intermediate: bool = False
    semantic_filter: bool = False          # Vaihe 2 legacy (geometric); käytä semantic_filter_mode
    semantic_filter_mode: Literal["off", "auto", "geometric", "pointnet", "pointnet-retail"] = "auto"
    # auto (oletus): kytkee PointNet-suodattimen VAIN liiketiloihin (iso pohja +
    # korkea tila = lattia-katto-hyllyt). Suodatin poistaa hyllyvaleseinät joita
    # geometria ei koko-mittaisille hyllyille pysty (mitattu: retail 2→0). Mutta
    # se REGRESSOI asuintaloa (poistaa aidon seinän+huoneen, mitattu talo 9→8/2→1
    # huonetta) → asunto/talo/rohbau (matala tila) pysyvät suodattamattomina eivätkä
    # hidastu. Kynnykset _RETAIL_MIN_* alla.
    # pointnet-retail: ALIAS "pointnet":lle. Erillinen liiketilamalli sulautettiin
    # yhteen malliin cb50610:ssä (geocol_v2_ms, koulutettu synteettisellä liiketila-
    # ja monikerrosdatalla; hyllynpoisto 15 % → 71 %, Rohbau-rakenne 0.879 → 0.947).
    # models/s3dis_pointnet_retail.onnx on tarkoituksella sama tiedosto. Säilytetään
    # yhteensopivuuden vuoksi; älä oleta sen suodattavan eri tavalla.
    # (95% vs oletusmallin 17%); asunnoissa oletusmalli on tarkempi.
    semantic_model_path: "Path | None" = None   # yliaja PointNet-mallitiedosto (esim. uuden mallin testaus)
    crs_epsg: int = 3067    # georef-leima IFC:hen (EPSG). Geometria pysyy skannin
                            # oikeissa koordinaateissa; ks. core/ifc/crs.py CRS_PRESETS.
                            # 0 = ei leimaa. Oletus ETRS-TM35FIN.


_AUTO_TARGET_POINTS = 4_000_000
_AUTO_VOXEL_MIN = 8.0
_AUTO_VOXEL_MAX = 25.0


def _drop_stale_floors(out_dir: Path, keep: int, progress=None) -> None:
    """Poista edellisen ajon ylimääräiset floor_NN-hakemistot.

    Kerrosjako voi muuttua ajojen välillä (esim. keksitty kerros korjattiin
    pois). Vanha `floor_01` jäisi levylle ja menisi `building.ifc`:hen mukaan,
    jolloin malli sisältäisi kerroksen jota nykyinen ajo ei tunnista.
    """
    import shutil

    for d in sorted(out_dir.glob("floor_[0-9][0-9]")):
        try:
            idx = int(d.name[-2:])
        except ValueError:
            continue
        if idx >= keep and d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            if progress:
                progress(f"  Poistettu vanhentunut {d.name}")


def _drop_stale_dxf(out_dir, progress=None) -> None:
    """Poista edellisen ajon model.dxf jos tämä ajo ei kirjoita DXF:ää.

    GUI ajaa export_dxf=False, joten DXF ei korvaudu. Ilman tätä kansioon jää
    vanha piirustus jota mikään ei merkitse vanhaksi — mitattu asunnosta: IFC
    oli 17.8. ja sen vieressä 22.6. DXF, eri mallista.
    """
    stale = out_dir / "model.dxf"
    try:
        if stale.is_file():
            stale.unlink()
            if progress:
                progress(f"  Poistettu vanhentunut {stale.name} (tämä ajo ei tuota DXF:ää)")
    except OSError as e:
        if progress:
            progress(f"  Vanhaa DXF:ää ei voitu poistaa: {e}")


def _auto_voxel(cloud, target: int = _AUTO_TARGET_POINTS) -> float:
    """Valitse voxelikoko niin että työpilvi on ~target pistettä (yksi halpa arvio)."""
    ref = 20.0
    n_ref = len(cloud.voxel_down_sample(ref).points)
    if n_ref <= target:
        return _AUTO_VOXEL_MIN
    v = ref * float(np.sqrt(n_ref / target))
    return round(min(max(v, _AUTO_VOXEL_MIN), _AUTO_VOXEL_MAX), 1)


def _xy_index(pts: np.ndarray, walls) -> "XYIndex | None":
    """Indeksi kannattaa vain kun työtä on: pieni pilvi tai yksi seinä ei hyödy."""
    if len(pts) < 300_000 or len(walls) < 3:
        return None
    from scan2bim.core.geometry.xy_index import XYIndex  # noqa: PLC0415
    return XYIndex(pts)


def _xy_subset(pts, index, p0, along, normal, radius, s_lo=-np.inf, s_hi=np.inf):
    if index is None:
        return pts, None
    from scan2bim.core.geometry.xy_index import subset  # noqa: PLC0415
    return subset(pts, index, p0, along, normal, radius, s_lo, s_hi)


def _recenter_wall_axes(walls, cloud, band: float | None = None, keep_thickness: bool = False) -> list:
    """Pintalukittu tarkennus: mallin lähin pinta osuu skannattuun pistepintaan (bias→0)."""
    pts = np.asarray(cloud.points)
    idx = _xy_index(pts, walls)
    return [_surface_lock_wall(w, pts, band=band, keep_thickness=keep_thickness, index=idx)
            for w in walls]


# --- Liiketilan tunnistus (semantic_filter_mode="auto") ---------------------
_RETAIL_MIN_AREA_M2 = 600.0     # m² — pienempi pohja = ei big-box-liiketila
_RETAIL_MIN_HEIGHT_MM = 4500.0  # mm — lattia-katto-hyllyt vaativat korkean tilan;
                                # asunto/talo/rohbau-kerros ~2400–3000 mm → alle rajan


def _looks_like_retail(cloud) -> bool:
    """True kun skene on iso JA korkea = big-box-liiketila (lattia-katto-hyllyt).

    Tunnistus tehdään ENNEN detektiota raakapilvestä: hyllyvaleseinien poisto
    (PointNet-suodatin) hyödyttää liiketilaa mutta regressoi asuintaloa, joten se
    kytketään vain kun sekä pohjan pinta-ala että vapaa korkeus ylittävät rajan.
    Korkeus on avainerotin: asuinkerros ~2.7 m jää aina alle 4.5 m rajan."""
    pts = np.asarray(cloud.points)
    if len(pts) < 1000:
        return False
    z = pts[:, 2]
    height = float(np.percentile(z, 99) - np.percentile(z, 1))
    if height < _RETAIL_MIN_HEIGHT_MM:
        return False
    x, y = pts[:, 0], pts[:, 1]
    dx = float(np.percentile(x, 99) - np.percentile(x, 1))
    dy = float(np.percentile(y, 99) - np.percentile(y, 1))
    area_m2 = (dx * dy) / 1.0e6
    return area_m2 >= _RETAIL_MIN_AREA_M2


_LARGE_SPACE_M2 = 400.0   # m² — tätä suurempi POHJA-ala (miehitetyt ruudut, ei
                          # tiheyspainotettu percentiili) → histogrammi-detektori.
                          # Isossa tilassa contour rakentaa seinät vain tiheän
                          # lattiakontuurin ympärille (skannerihuone); histogrammi
                          # nappaa koko rakennusvaipan keskikorkeuden tiheydestä.


def _occupancy_area_m2(cloud, cell: float = 1000.0, min_pts: int = 3) -> float:
    """Tilan POHJA-ala miehitettyinä xy-ruutuina — tiheysriippumaton (harvaan
    keilattu kaukoseinä lasketaan). Percentiili-ala aliarvioi kun skannerit ovat
    yhdessä huoneessa (tiheä alue dominoi); miehitysala näkee koko rakennuksen."""
    pts = np.asarray(cloud.points)
    if len(pts) < 1000:
        return 0.0
    g = np.floor(pts[:, :2] / cell).astype(np.int64)
    key = g[:, 0] * 2_000_003 + g[:, 1]
    _, counts = np.unique(key, return_counts=True)
    return float((counts >= min_pts).sum()) * (cell / 1000.0) ** 2


def _trim_wall_endpoints(walls, cloud) -> list:
    """Trimmaa seinien päätepisteet vastaamaan todellista pistepilvidataa."""
    pts = np.asarray(cloud.points)
    idx = _xy_index(pts, walls)
    return [_trim_endpoints(w, pts, index=idx) for w in walls]


def _trim_endpoints(wall, pts: np.ndarray, index=None):
    if len(wall.axis) < 2:
        return wall
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 1.0:
        return wall

    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    axis_D = float(np.dot(normal, p0))

    half_t = wall.thickness / 2.0
    face_tol = 30.0
    # KESKIKORKEUS, ei koko korkeus: seinän x-kaistalla on myös LATTIA- ja
    # KATTOLAATAN pisteitä (laatta ulottuu joka y:hyn), jotka saisivat seinän
    # näyttämään jatkuvan koko tilan syvyyden → päätepistettä ei voi mitata.
    # Keskikorkeudella (0.25–0.75 H) on vain seinäpinta + pystyrakenteet.
    z_lo = wall.z_min + 0.25 * wall.height
    z_hi = wall.z_min + 0.75 * wall.height

    # Akselin suuntaan EI rajausta: percentiilit lasketaan kaikista pinnalle
    # osuvista pisteistä, myös janan päiden ulkopuolelta (juuri siitä pidennys
    # tulee) — rajaus muuttaisi tulosta.
    pts, _ = _xy_subset(pts, index, p0, along, normal, half_t + face_tol)
    if len(pts) < 20:
        return wall

    dist = np.abs(pts[:, :2] @ normal - axis_D)
    along_proj = (pts[:, :2] - p0) @ along

    # Ota pisteet seinän pinnoilta (±30mm käy)
    on_face = (
        ((np.abs(dist - half_t) < face_tol) | (dist < face_tol))
        & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    )
    if on_face.sum() < 20:
        return wall

    face_along = along_proj[on_face]
    lo = float(np.percentile(face_along, 2))
    hi = float(np.percentile(face_along, 98))

    _MARGIN = 5.0        # mm — pieni reuna päätepisteiden ympärillä
    _MAX_EXTEND = 300.0  # mm — älä pidennä yli tämän (T-liitos tai dataaukko)
    _MAX_TRIM = 300.0    # mm/pää — älä kutista enempää: datattoman seinän kaistaan
                         # osuu vain RISTEÄVIEN seinien pisteitä → percentiilit
                         # romahduttaisivat koko seinän risteyskohtaan

    # ...PAITSI kun [lo,hi] on kiistatta aito seinäpinta: pitkä (>=2.5 m) JA
    # tiheä (>=300 pintapistettä). Silloin percentiilit eivät ole risteyspiste-
    # rypäs vaan seinän todelliset reunat → poikkeuksellisen pitkä haamuylitys
    # (esim. isossa myymälässä 10–30 m akselin jatke tyhjän lattian yli) saadaan
    # leikattua. Lyhyt/harva kaista pysyy 300 mm cap:n suojassa (romahdussuoja).
    _TRUST_SPAN = 2500.0  # mm
    _TRUST_PTS = 300
    trust = (hi - lo) >= _TRUST_SPAN and int(on_face.sum()) >= _TRUST_PTS
    trim_cap = 1e12 if trust else _MAX_TRIM

    ax = [list(wall.axis[0]), list(wall.axis[1])]
    changed = False

    # p0: trimmaa jos data alkaa sisempänä, pidennä jos data alkaa ulompana
    if lo > _MARGIN:
        new_p0 = p0 + min(lo - _MARGIN, trim_cap) * along
        ax[0] = [round(float(new_p0[0]), 1), round(float(new_p0[1]), 1)]
        changed = True
    elif lo < -_MARGIN and abs(lo) <= _MAX_EXTEND:
        new_p0 = p0 + (lo + _MARGIN) * along
        ax[0] = [round(float(new_p0[0]), 1), round(float(new_p0[1]), 1)]
        changed = True

    # p1: trimmaa jos data loppuu sisempänä, pidennä jos data jatkuu ulompana
    if hi < length - _MARGIN:
        new_p1 = p0 + max(hi + _MARGIN, length - trim_cap) * along
        ax[1] = [round(float(new_p1[0]), 1), round(float(new_p1[1]), 1)]
        changed = True
    elif hi > length + _MARGIN and (hi - length) <= _MAX_EXTEND:
        new_p1 = p0 + (hi - _MARGIN) * along
        ax[1] = [round(float(new_p1[0]), 1), round(float(new_p1[1]), 1)]
        changed = True

    return wall.model_copy(update={"axis": ax}) if changed else wall


# --- pintalukittu tarkennus -------------------------------------------------
# Tavoite: mallin LÄHIN pinta osuu skannattuun pistepintaan, ei thickness/2 ohi.
# Yksipuolisesti keilatuille seinille (sisätilakeilaus) detektoitu akseli istuu
# pinnan päällä; symmetrinen paksuus työntäisi pinnan ~thickness/2 ohi. Lukitaan
# lähin pinta huippuun ja kasvatetaan paksuus huoneesta POISPÄIN.

_SL_BAND = 280.0           # mm — kohtisuora hakukaista (kapea: ei naapuriseinää)
_SL_MIN_PTS = 60           # min pisteitä jotta tarkennetaan
_SL_BIN = 5.0              # mm histogrammin resoluutio
_SL_MIN_THICK = 60.0       # mm
_SL_MAX_THICK = 380.0      # mm
_SL_DEFAULT_THICK = 120.0  # mm — sisäväliseinän oletus kun toista pintaa ei nähdä
_SL_DOM_BAND = 120.0       # mm — dominantti pinta haetaan akselin läheltä (detektori jättää akselin pinnalle)
_SL_PARTNER_FRAC = 0.45    # toisen pinnan oltava väh. tämä osuus dominantin pisteistä → aito pari
_SL_ROOM_LO = 150.0        # mm — huonepuolen pisteenlaskenta alkaa tästä huipusta
_SL_ROOM_HI = 700.0        # mm — ja päättyy tähän


def _fix_wall_center(wall, pts: np.ndarray):
    """Vanha nimi taaksepäinyhteensopivuudelle; delegoi pintalukitukseen."""
    return _surface_lock_wall(wall, pts)


def _surface_lock_wall(wall, pts: np.ndarray, band: float | None = None,
                       keep_thickness: bool = False, index=None):
    sl_band = band if band is not None else _SL_BAND
    if len(wall.axis) < 2:
        return wall
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 1.0:
        return wall

    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    axis_D = float(np.dot(normal, p0))

    z_lo = wall.z_min + 200.0
    z_hi = wall.z_min + wall.height - 200.0
    pts, _ = _xy_subset(pts, index, p0, along, normal, sl_band, 100.0, length - 100.0)
    if len(pts) < _SL_MIN_PTS:
        return wall
    along_proj = (pts[:, :2] - p0) @ along
    dist = pts[:, :2] @ normal - axis_D

    mask = (
        (along_proj >= 100.0) & (along_proj <= length - 100.0)
        & (np.abs(dist) <= sl_band)
        & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    )
    if mask.sum() < _SL_MIN_PTS:
        return wall

    d_vals = dist[mask]
    edges = np.arange(-sl_band, sl_band + _SL_BIN, _SL_BIN)
    hist, edges = np.histogram(d_vals, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    smooth = uniform_filter1d(hist.astype(float), size=3)
    pks, _ = find_peaks(smooth, height=smooth.max() * 0.20, distance=4)
    if len(pks) == 0:
        return wall

    # Dominantti SKANNATTU pinta: vahvin huippu akselin läheltä. Detektoiduilla
    # seinillä akseli on pinnan päällä → rajaa ±_SL_DOM_BAND (ei naapuriseinää).
    if keep_thickness:
        # Perimetriseinä: akseli on jo siirretty ULOS thickness/2, joten odotettu
        # SISÄPINTA on ~+thickness/2 kohdalla. Etsi huippu sen ympäriltä → pieni
        # korjaus oikeaan sisäpintaan, ei naapuriseinän nappaamista väärältä puolelta.
        exp = wall.thickness / 2.0
        win = 100.0
        cand = [p for p in pks if abs(float(centers[p]) - exp) <= win]
        if not cand:
            return wall
        dom = int(max(cand, key=lambda p: smooth[p]))
    else:
        near = [p for p in pks if abs(float(centers[p])) <= _SL_DOM_BAND]
        cand = near if near else list(pks)
        dom = int(max(cand, key=lambda p: smooth[p]))
    surf = float(centers[dom])
    dom_h = float(smooth[dom])

    # Toinen pinta: lähin riittävän vahva huippu joka antaa järkevän paksuuden.
    # Vaaditaan että sillä on oikeasti pisteitä (PARTNER_FRAC dominantista),
    # muuten kyseessä on yksipuolinen seinä eikä kohinapiikki/naapuri.
    # keep_thickness (perimetriseinä): pakota yksipuolinen haara → lukitse vain
    # sisäpinta, säilytä annettu paksuus (ei naapuriseinän nappaamista).
    best_partner: int | None = None
    best_t = 1e9
    if not keep_thickness:
        for q in pks:
            if int(q) == dom:
                continue
            t_pair = abs(float(centers[q]) - surf)
            if not (_SL_MIN_THICK <= t_pair <= _SL_MAX_THICK):
                continue
            if float(smooth[q]) < _SL_PARTNER_FRAC * dom_h:
                continue
            if t_pair < best_t:
                best_t = t_pair
                best_partner = int(q)

    if best_partner is not None:
        # KAKSI pintaa nähty → akseli pintojen puoliväliin, paksuus = pintaero.
        other = float(centers[best_partner])
        t_new = abs(surf - other)
        center_offset = 0.5 * (surf + other)
    elif keep_thickness:
        # Perimetriseinä: surf = todellinen SISÄPINTA (etsitty +thickness/2:n läheltä).
        # Lukitse sisäpinta siihen, säilytä paksuus → akseli = surf - thickness/2.
        t_new = wall.thickness
        room_sign = 1.0 if surf >= 0.0 else -1.0
        center_offset = surf - room_sign * (t_new / 2.0)
    else:
        # YKSI pinta → lukitse lähin (huoneenpuoleinen) pinta huippuun. Huoneen
        # puoli = enemmän pisteitä huipun takana (avoin tila); seinärunko menee
        # siitä poispäin → mallin lähin pinta osuu skannattuun pintaan (bias→0).
        left = float(((d_vals > surf - _SL_ROOM_HI) & (d_vals < surf - _SL_ROOM_LO)).sum())
        right = float(((d_vals > surf + _SL_ROOM_LO) & (d_vals < surf + _SL_ROOM_HI)).sum())
        room_sign = 1.0 if right >= left else -1.0
        t_new = wall.thickness
        if not (_SL_MIN_THICK <= t_new <= _SL_MAX_THICK):
            t_new = _SL_DEFAULT_THICK
        center_offset = surf - room_sign * (t_new / 2.0)

    if not (_SL_MIN_THICK <= t_new <= _SL_MAX_THICK):
        return wall

    updates: dict = {}
    if abs(center_offset) >= 0.5:
        shift_vec = center_offset * normal
        updates["axis"] = [
            [round(p0[0] + shift_vec[0], 1), round(p0[1] + shift_vec[1], 1)],
            [round(p1[0] + shift_vec[0], 1), round(p1[1] + shift_vec[1], 1)],
        ]
    if abs(t_new - wall.thickness) >= 1.0:
        updates["thickness"] = round(t_new, 1)

    return wall.model_copy(update=updates) if updates else wall


# --- LOA-tarkka PAKSUUS raakapisteistä --------------------------------------
# Tavoite: kaksipuolisen seinän PAKSUUS <1.5mm. Mitataan molempien pintojen
# kohtisuora signed-distance -huippu täysiresan/3mm raakapisteistä, ali-bin
# tarkkuudella (parabolinen huipun interpolointi) → paksuus = huippujen ero,
# akseli pintojen puoliväliin. Yksipuolinen seinä (vain yksi pinta näkyvissä) →
# paksuutta ei muuteta (ei mitattavissa pilvestä). Ajetaan VIIMEISENÄ
# tarkennuksena hienolla pilvellä; detektio + huoneet pysyvät 12mm:ssä.

# Mittausikkuna seuraa QA-mittaria (_element_qa.py) jotta malli ja mittari ovat
# samaa mieltä kahdesta pinnasta: ±200mm kohtisuora, 2mm bini, top-2 huippua.
_TL_SEARCH = 200.0       # mm — kohtisuora hakukaista akselista (= QA 200)
_TL_BIN = 2.0            # mm — hieno histogrammiresoluutio (= QA 2mm)
_TL_MIN_PTS = 500        # min raakapisteitä kaistassa (= QA 500)
_TL_MIN_THICK = 50.0     # mm (= QA 50)
_TL_MAX_THICK = 400.0    # mm (= QA 400)
_TL_PEAK_FRAC = 0.25     # huipun min korkeus suhteessa maksimiin (= QA 0.25)
_TL_WEAK_FRAC = 0.08     # heikko vastapinta hyväksytään jos istuu odotetussa paikassa
                         # (epäsymmetrinen näkyvyys: toinen puoli skannattu kauempaa)
_TL_ALONG_MARGIN = 400.0 # mm — along-suunnan ylitys (= QA -400..L+400)
_TL_FACE_WIN = 60.0      # mm — yksipuolinen: huipun oltava näin lähellä odotettua
_TL_BODY_MIN_T = 210.0   # mm — runkotesti vain tätä paksummalle parille (ohuemman
                         # rungosta ei voi mitata: pintakohina täyttää kaistan)
_TL_BODY_MARGIN = 45.0   # mm — pintakohinan marginaali rungon sisään
_TL_BODY_FRAC = 0.60     # kattoa yli tämän osuuden rungosta → pari ei kelpaa
_TL_BODY_ZBAND = 60.0    # mm — ±kaista kattotason ympärillä
_TL_ONE_SIDED_T = 200.0  # mm — hylätyn valeparin jälkeen: yksipuolisen oletuspaksuus
_TL_UNSUPPORTED_REACH = 120.0  # mm — kuinka kauas valepaksuuden ulkopuolelta ainoa
                               # pinta saa löytyä ennen kuin akseli siirretään sille
                         # mallipintaa (±th/2), muuten se on naapuri/kaluste → ei lukita


def _parabolic_peak(hist: np.ndarray, centers: np.ndarray, pk: int) -> float:
    """Ali-bin huipun paikka parabolisella interpoloinnilla (bin-keskeltä pois)."""
    if pk <= 0 or pk >= len(hist) - 1:
        return float(centers[pk])
    y0, y1, y2 = float(hist[pk - 1]), float(hist[pk]), float(hist[pk + 1])
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-9:
        return float(centers[pk])
    delta = 0.5 * (y0 - y2) / denom
    bin_w = float(centers[1] - centers[0])
    return float(centers[pk]) + max(-1.0, min(1.0, delta)) * bin_w


def _thickness_lock_walls(walls, cloud, iters: int = 3, ceiling_xy=None) -> list:
    # Iteroi: akselin keskitys siirtää mittausikkunaa → mittaus tarkentuu kun
    # akseli osuu pintojen puoliväliin. 1 kierros ~2mm mediaani, 3 kierrosta
    # ~1.15mm (suppenee). Halpa (sama pilvi muistissa).
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return walls
    ceil_xy = None if ceiling_xy is None or len(ceiling_xy) == 0 else np.asarray(ceiling_xy)
    inside = pts[:, :2].mean(axis=0)
    idx = _xy_index(pts, walls)
    for _ in range(iters):
        walls = [_thickness_lock_wall(w, pts, ceil_xy, inside, index=idx) for w in walls]
    return walls


def _ceiling_band_xy(cloud, ceiling_z: float | None) -> np.ndarray | None:
    """Kattotason XY-pisteet. Paksuusmittauksen `thick_cloud` on VAIN keskikaista
    (35–65 % z-alueesta) → siinä ei ole kattoa lainkaan, joten runkotesti tarvitsee
    oman pilven."""
    if cloud is None or ceiling_z is None:
        return None
    pts = np.asarray(cloud.points)
    if len(pts) == 0:
        return None
    sel = np.abs(pts[:, 2] - ceiling_z) < _TL_BODY_ZBAND
    return pts[sel, :2] if sel.any() else None


def _pair_body_has_ceiling(
    ceiling_xy: np.ndarray | None, p0: np.ndarray, along: np.ndarray, normal: np.ndarray,
    length: float, center: float, t_new: float,
) -> bool:
    """Pintapari ei kelpaa jos seinän RUNGON sisällä on kattoa.

    Yksipuolisella (ulko)seinällä huoneen puolella oleva kaluste — kaappi/hylly
    ~300 mm pinnasta — tuottaa toisen piikin. Pari paisuttaa paksuuden ja siirtää
    akselin puoli paksuutta HUONEEN sisään; naapuripätkä jää eri linjalle eikä
    merge_collinear enää sulauta niitä → huone ei sulkeudu. Katossa ei ole
    kalusteita, joten kattoa rungon sisällä = runko on osittain huonetilaa.
    Mitattu asunnolla: valepari 0.93–0.97, aidot ≤0.52."""
    if ceiling_xy is None or t_new < _TL_BODY_MIN_T or length < 800.0:
        return False
    half = t_new / 2.0 - _TL_BODY_MARGIN
    if half <= 60.0:
        return False
    rel = ceiling_xy - p0
    s = rel @ along
    t = rel @ normal
    m = (s > 150.0) & (s < length - 150.0) & (np.abs(t - center) < half)
    if not m.any():
        return False
    n_bins = max(int(length // 250.0), 1)
    hist, _ = np.histogram(s[m], bins=n_bins, range=(0.0, length))
    return float((hist > 3).mean()) > _TL_BODY_FRAC


def _single_face_lock(wall, hist, centers, pks, normal, p0, p1, inward=None):
    """Yksipuolinen seinä: lukitse NÄKYVÄ pinta ali-bin-tarkkuudella.

    Kaksipuolinen mittaus ei ole mahdollinen (vain yksi pinta keilattu), mutta
    pinnan SIJAINTI on — aiemmin nämä seinät jäivät 12mm-voxelin recenterin
    varaan (~2–4mm pintavirhe). Vahvin huippu odotetun mallipinnan (±th/2)
    läheltä → siirrä akselia niin että mallipinta osuu huippuun. Paksuus ei muutu."""
    if not len(pks):
        return wall
    half_t = wall.thickness / 2.0
    cands = []  # (virhe, korkeus, pk, odotettu_pinta)
    for pk in pks:
        f = float(centers[pk])
        for face in (half_t, -half_t):
            err = abs(f - face)
            if err <= _TL_FACE_WIN:
                cands.append((err, float(hist[pk]), int(pk), face))
    if not cands:
        return _unsupported_thickness_lock(wall, hist, centers, pks, normal, p0, p1, inward)
    # LÄHIN riittävän vahva piikki, ei vahvin: verho/karmi huoneen puolella voi
    # olla vahvempi piikki 40–60mm päässä — pintalukituksen on osuttava seinään.
    h_max = max(c[1] for c in cands)
    cands = [c for c in cands if c[1] >= 0.4 * h_max]
    err, _, pk, face = min(cands)
    f_sub = _parabolic_peak(hist, centers, pk)
    shift = f_sub - face
    if abs(shift) < 0.2:
        return wall
    shift_vec = shift * normal
    return wall.model_copy(update={"axis": [
        [round(p0[0] + shift_vec[0], 2), round(p0[1] + shift_vec[1], 2)],
        [round(p1[0] + shift_vec[0], 2), round(p1[1] + shift_vec[1], 2)],
    ]})


def _unsupported_thickness_lock(wall, hist, centers, pks, normal, p0, p1, inward):
    """Paksuus jota YKSIKÄÄN pinta ei tue → yksipuolinen seinä, runko ulospäin.

    Kontuurimaskissa yksipuolinen pinta on 1 px viiva, jonka 5×5-closing paisuttaa
    ~3 px kaistaksi; `_merge_axis_lines` lukee kaistan kaksi reunaa kahdeksi
    pinnaksi ja tuottaa 66–92 mm "paksuuden". Raakapisteissä pintoja on vain YKSI,
    joten `_thickness_lock_wall` ei löydä toista huippua eikä yllä oleva ±60 mm
    ikkuna yletä valepaksuuden yli → seinä jäi ennen KORJAAMATTA sinne minne
    detektori sen laittoi. Mitattu synteettisellä 72×48 m myymälällä: 72 m
    ulkoseinä 57.4 mm ja 21 m ulkoseinä 62.1 mm pinnastaan (`_tol_heatmap`),
    kaikki muut ≤4.5 mm.

    Korjaus: aseta paksuudeksi yksipuolisen oletus ja siirrä akseli niin että
    NÄKYVÄ pinta osuu mitattuun huippuun. Runko kasvaa poispäin pilven
    massakeskipisteestä (= ulospäin rakennuksesta). Mittaamaton puoli on arvaus
    joka tapauksessa; näkyvä pinta on tämän jälkeen oikeassa paikassa."""
    if inward is None or wall.thickness >= _TL_ONE_SIDED_T:
        return wall
    dom = int(max(pks, key=lambda p: hist[p]))
    f = _parabolic_peak(hist, centers, dom)
    if abs(f) > wall.thickness / 2.0 + _TL_UNSUPPORTED_REACH:
        return wall
    side = -1.0 if float(np.dot(inward - p0, normal)) >= 0.0 else 1.0
    center = f + side * _TL_ONE_SIDED_T / 2.0
    shift_vec = center * normal
    return wall.model_copy(update={
        "axis": [
            [round(p0[0] + shift_vec[0], 2), round(p0[1] + shift_vec[1], 2)],
            [round(p1[0] + shift_vec[0], 2), round(p1[1] + shift_vec[1], 2)],
        ],
        "thickness": _TL_ONE_SIDED_T,
    })


def _thickness_lock_wall(wall, pts: np.ndarray, ceiling_xy: np.ndarray | None = None,
                         inward: np.ndarray | None = None, index=None):
    if len(wall.axis) < 2:
        return wall
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0))
    if length < 200.0:
        return wall

    along = (p1 - p0) / length
    normal = np.array([-along[1], along[0]])
    axis_D = float(np.dot(normal, p0))

    z_lo = wall.z_min + 200.0
    z_hi = wall.z_min + wall.height - 200.0
    pts, _ = _xy_subset(pts, index, p0, along, normal, _TL_SEARCH,
                        -_TL_ALONG_MARGIN, length + _TL_ALONG_MARGIN)
    if len(pts) < _TL_MIN_PTS:
        return wall
    along_proj = (pts[:, :2] - p0) @ along
    dist = pts[:, :2] @ normal - axis_D

    mask = (
        (along_proj >= -_TL_ALONG_MARGIN) & (along_proj <= length + _TL_ALONG_MARGIN)
        & (np.abs(dist) <= _TL_SEARCH)
        & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi)
    )
    if mask.sum() < _TL_MIN_PTS:
        return wall

    d = dist[mask]
    edges = np.arange(-_TL_SEARCH, _TL_SEARCH + _TL_BIN, _TL_BIN)
    hist, edges = np.histogram(d, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    pks, _ = find_peaks(hist, height=hist.max() * _TL_PEAK_FRAC, distance=int(20.0 / _TL_BIN))
    if len(pks) == 0:
        return _single_face_lock(wall, hist, centers, pks, normal, p0, p1, inward)

    # Seinän kaksi pintaa = kaksi vahvinta huippua (sama valinta kuin QA-mittari
    # _element_qa.py, jotta malli ja mittari ovat samaa mieltä). Ali-bin tarkkuus
    # parabolisella interpoloinnilla → <1.5mm vaikka bini on 2mm.
    dom = int(max(pks, key=lambda p: hist[p]))
    second: int | None = None
    if len(pks) >= 2:
        cand = sorted((int(p) for p in pks if int(p) != dom), key=lambda p: hist[p], reverse=True)[0]
        if _TL_MIN_THICK <= abs(float(centers[dom]) - float(centers[cand])) <= _TL_MAX_THICK:
            second = cand

    if second is None:
        # Epäsymmetrinen näkyvyys: takapinta skannattu kauempaa/harvemmin ja jää
        # 25%-kynnyksen alle vaikka on aito (rohbau: 27% vs 550k etupistettä →
        # 22mm virhe). Hyväksy heikompi piikki (≥_TL_WEAK_FRAC) jos se istuu
        # odotetun VASTAPINNAN kohdalla (±_TL_FACE_WIN detektoidusta paksuudesta).
        weak, _ = find_peaks(hist, height=hist.max() * _TL_WEAK_FRAC, distance=int(20.0 / _TL_BIN))
        expected = (float(centers[dom]) - wall.thickness, float(centers[dom]) + wall.thickness)
        cands = [
            int(p) for p in weak
            if int(p) != dom and min(abs(float(centers[p]) - e) for e in expected) <= _TL_FACE_WIN
        ]
        if cands:
            second = max(cands, key=lambda p: hist[p])

    if second is None:
        return _single_face_lock(wall, hist, centers, pks, normal, p0, p1, inward)

    f_dom = _parabolic_peak(hist, centers, dom)
    f_sec = _parabolic_peak(hist, centers, second)
    t_new = abs(f_dom - f_sec)
    if not (_TL_MIN_THICK <= t_new <= _TL_MAX_THICK):
        return wall
    center_offset = 0.5 * (f_dom + f_sec)

    if _pair_body_has_ceiling(ceiling_xy, p0, along, normal, length, center_offset, t_new):
        # Toinen "pinta" on kaluste huoneen sisällä → yksipuolinen seinä. Pelkkä
        # paksuuden säilyttäminen ei riitä: akseli jäisi puoli VALEpaksuutta
        # huoneen sisään eikä naapuripätkä enää sulaudu samalle linjalle.
        # Runko kasvaa NÄKYVÄSTÄ pinnasta poispäin kalusteen puolelta.
        t_one = wall.thickness if wall.thickness < _TL_BODY_MIN_T else _TL_ONE_SIDED_T
        side = 1.0 if f_dom >= f_sec else -1.0
        center = f_dom + side * t_one / 2.0
        shift_vec = center * normal
        return wall.model_copy(update={
            "axis": [
                [round(p0[0] + shift_vec[0], 2), round(p0[1] + shift_vec[1], 2)],
                [round(p1[0] + shift_vec[0], 2), round(p1[1] + shift_vec[1], 2)],
            ],
            "thickness": round(t_one, 1),
        })

    updates: dict = {}
    if abs(center_offset) >= 0.2:
        shift_vec = center_offset * normal
        updates["axis"] = [
            [round(p0[0] + shift_vec[0], 2), round(p0[1] + shift_vec[1], 2)],
            [round(p1[0] + shift_vec[0], 2), round(p1[1] + shift_vec[1], 2)],
        ]
    if abs(t_new - wall.thickness) >= 0.2:
        updates["thickness"] = round(t_new, 1)
    return wall.model_copy(update=updates) if updates else wall


def _count_disjoint_regions(cloud, grid_mm: float = 500.0, min_area_m2: float = 4.0) -> int:
    """Montako erillistä XY-aluetta pilvessä on (yhtenäisyys 0.5m-ruudukolla)."""
    from scipy.ndimage import label
    pts = np.asarray(cloud.points)
    if len(pts) < 1000:
        return 1
    xy = pts[:, :2]
    x0, y0 = xy[:, 0].min(), xy[:, 1].min()
    nx = int((xy[:, 0].max() - x0) / grid_mm) + 1
    ny = int((xy[:, 1].max() - y0) / grid_mm) + 1
    if nx * ny > 4_000_000:
        return 1
    H, _, _ = np.histogram2d(
        xy[:, 0], xy[:, 1], bins=[nx, ny],
        range=[[x0, x0 + nx * grid_mm], [y0, y0 + ny * grid_mm]],
    )
    occ = H >= 3
    labels, n = label(occ, structure=np.ones((3, 3), dtype=int))
    min_cells = int(min_area_m2 * 1e6 / (grid_mm * grid_mm))
    big = sum(1 for k in range(1, n + 1) if int((labels == k).sum()) >= min_cells)
    return max(big, 1)


_ENVELOPE_CELL_MM = 200.0
_ENVELOPE_ROOF_MIN_MM = 2000.0   # piste yli tämän lattiasta = katto/räystäs
_ENVELOPE_DILATE_CELLS = 0       # detektio rajataan katetun alueen sisään; ulkopinnat tulevat thick_cloudista
_ENVELOPE_MIN_REMOVE_FRAC = 0.10  # rajaa vain jos poisto ≥ tämä (= selvästi ulkodataa; suojaa avointa runkoa)


def _crop_to_building_envelope(cloud):
    """Poistaa katteettoman ULKOalueen (maasto/piha/kasvillisuus/ulkoklutteri)
    ennen kontuuria. Rakennuksen sisätila on katolla peitetty, ulkomaasto on
    avoin taivaalle: katon 2D-peitto (dilatoituna) = rakennuksen vaippa → sen
    ulkopuoliset pisteet pois. Ilman tätä ulkoskanni räjäyttää footprintin ja
    maanpinta voittaa lattiapiikin (mitattu synteettisellä: footprint 6→16 m,
    lattia 0→−150 mm, 4 jättivaleseinää).

    Sisätila-only-datalla katto peittää koko footprintin → EI poista mitään
    (no-op). Ulkoseinien ulkopinnat säilyvät dilataation ansiosta; paksuus
    mitataan joka tapauksessa erillisestä (rajaamattomasta) thick_cloudista."""
    from scipy.ndimage import binary_dilation
    pts = np.asarray(cloud.points)
    if len(pts) < 2000:
        return cloud
    z0 = float(np.percentile(pts[:, 2], 1.0))
    roof = pts[pts[:, 2] > z0 + _ENVELOPE_ROOF_MIN_MM]
    if len(roof) < 200:
        return cloud  # kattoa ei erotettavissa (matala tila) → älä koske
    origin = pts[:, :2].min(axis=0)
    pc = np.floor((pts[:, :2] - origin) / _ENVELOPE_CELL_MM).astype(np.int64)
    rc = np.floor((roof[:, :2] - origin) / _ENVELOPE_CELL_MM).astype(np.int64)
    nx = int(pc[:, 0].max()) + 2
    ny = int(pc[:, 1].max()) + 2
    mask = np.zeros((nx, ny), dtype=bool)
    mask[rc[:, 0], rc[:, 1]] = True
    if _ENVELOPE_DILATE_CELLS >= 1:
        mask = binary_dilation(mask, iterations=_ENVELOPE_DILATE_CELLS)
    inside = mask[pc[:, 0], pc[:, 1]]
    n_in = int(inside.sum())
    if n_in < 2000:
        return cloud  # arvio meni pieleen → älä tyhjennä pilveä
    if (len(pts) - n_in) < _ENVELOPE_MIN_REMOVE_FRAC * len(pts):
        return cloud  # vähän katteetonta → sisätila/runko-only → no-op (suojaa avointa runkoa)
    return cloud.select_by_index(np.where(inside)[0])


def _align_faces_to_surface_median(walls, cloud) -> list:
    """Viimeinen pintalinjaus SAMALLA estimaattorilla kuin QA-mittari:
    dominantin puolen pistepinnan MEDIAANI koko seinäkorkeudelta.

    Histogrammihuippu (thickness_lock) ja mediaani eroavat 3–6 mm kun seinä on
    kallellaan tai kohina vinoa — pystyprisman paras sovitus koko korkeudelle
    on mediaani, ja QA mittaa sitä. Siirtää akselia vain sivusuunnassa."""
    _FACE_MAD_MAX = 20.0   # mm — pisteiden mediaanihajonta pinnan ympärillä; yli = ei pintaa
    _FACE_ONE_SIDED_FRAC = 0.10   # vastapinnan osuus dominantista → alle tämän = yksipuolinen
    _FACE_SINGLE_PLANE = 0.80     # dominantin puolen pisteistä ±30 mm mediaanista
    pts_all = np.asarray(cloud.points)
    if len(pts_all) == 0:
        return walls
    index = _xy_index(pts_all, walls)
    out = []
    for w in walls:
        if len(w.axis) < 2:
            out.append(w)
            continue
        p0 = np.array(w.axis[0], float)
        p1 = np.array(w.axis[1], float)
        L = float(np.linalg.norm(p1 - p0))
        if L < 1.0:
            out.append(w)
            continue
        u = (p1 - p0) / L
        n = np.array([-u[1], u[0]])
        pts, _ = _xy_subset(pts_all, index, p0, u, n,
                            w.thickness / 2.0 + 80.0, 100.0, L - 100.0)
        if len(pts) < 200:
            out.append(w)
            continue
        rel = pts[:, :2] - p0
        t = rel @ u
        perp = rel @ n
        zm = (pts[:, 2] > w.z_min + 200.0) & (pts[:, 2] < w.z_min + w.height - 200.0)
        band = zm & (t > 100.0) & (t < L - 100.0) & (np.abs(perp) < w.thickness / 2.0 + 80.0)
        if band.sum() < 200:
            out.append(w)
            continue
        s = perp[band]
        side = s > 0
        dom = s[side] if side.sum() >= (~side).sum() else s[~side]
        med = float(np.median(dom))
        # Pintaevidenssi: aidolla pinnalla pisteet keskittyvät mediaanin
        # ympärille (MAD ≈ 0.7×kohina-RMS ≤ ~13mm); tasainen jakauma = kaistassa
        # on massoa muttei seinäpintaa (telineet/tavara) → mediaanilinjaus olisi
        # fiktiota. Puolitetaan confidence → QA nostaa tarkistettavaksi
        # (perimetri 0.5 → 0.25 < 0.4).
        mad = float(np.median(np.abs(dom - med)))
        if mad > _FACE_MAD_MAX:
            out.append(w.model_copy(update={"confidence": round(w.confidence * 0.5, 3)}))
            continue
        core = dom[np.abs(dom - med) < 60.0]
        if len(core) > 50:
            med = float(np.median(core))
        face = w.thickness / 2.0 if med > 0 else -w.thickness / 2.0
        shift = med - face
        # Mitatun seinän akseli on jo ~oikein → iso siirto olisi väärä pinta
        # (cap 25mm). Perimetriseinän sijainti tulee lattiakontuurigridistä
        # (25mm ruutu + dilaatio ~75mm biasta) → salli isompi korjaus puhtaalle
        # pinnalle, muuten seinä jää kymmeniä mm pieleen eikä mikään flägää sitä.
        max_shift = 90.0 if w.source.method == "floorplan" else 25.0
        # YKSIPUOLINEN + YKSI SELVÄ PINTA: 25 mm katto oletti että akseli on jo
        # ~oikein, mikä pitää kaksipuoliselle seinälle (pinnat kiinnittävät sen).
        # Yksipuolisella mikään ei kiinnitä: mitattu synteettisellä 72×48 m
        # myymälällä 72 m ja 21 m ulkoseinä 57.4 ja 62.1 mm pinnastaan — tämä
        # vaihe MITTASI virheen oikein ja jätti sen korjaamatta cappiin.
        # Väärän pinnan riski tulee kilpailevista pinnoista kaistassa; kun
        # toisella puolella ei ole pintaa ja dominantti puoli on yksi tiivis
        # taso, kilpailijaa ei ole → korjaus saa yltää kaistan reunaan asti.
        n_dom, n_oth = int(side.sum()), int((~side).sum())
        if n_dom < n_oth:
            n_dom, n_oth = n_oth, n_dom
        if (n_oth < _FACE_ONE_SIDED_FRAC * n_dom
                and float(np.mean(np.abs(dom - med) < 30.0)) >= _FACE_SINGLE_PLANE):
            max_shift = w.thickness / 2.0 + 80.0
        if abs(shift) < 0.2 or abs(shift) > max_shift:
            out.append(w)
            continue
        sv = shift * n
        out.append(w.model_copy(update={"axis": [
            [round(p0[0] + sv[0], 2), round(p0[1] + sv[1], 2)],
            [round(p1[0] + sv[0], 2), round(p1[1] + sv[1], 2)],
        ]}))
    return out


_STD_THICK = [66.0, 92.0, 120.0, 150.0, 200.0, 250.0, 300.0]
_STD_SNAP_TOL = 12.0     # mm — snap standardiin vain tämän sisältä; kauempana
                         # mitattu arvo jää toimitusarvoksi (pinnat ≤1.5mm voittaa
                         # "siistin" paksuuslistan kun todellisuus poikkeaa selvästi)


def _snap_delivery_thickness(walls, cloud) -> list:
    """Toimituspaksuus standardiin, akseli ankkuroituna skannattuun pintaan.

    Dominantti (eniten pisteitä) pinta = se jonka arkkitehti näkee ja johon
    pintalukitus osui — sen on pysyttävä paikallaan. Paksuusmuutos kasvaa/
    kutistuu näkymättömälle puolelle: akseli siirtyy ±(snap-mitattu)/2 siihen
    suuntaan. Jos dominanttia puolta ei voi päätellä (ei pisteitä), snap on
    symmetrinen kuten ennen."""
    pts = np.asarray(cloud.points)
    out = []
    for w in walls:
        measured = round(w.thickness, 1)
        snapped = min(_STD_THICK, key=lambda s: abs(s - w.thickness))
        # Snap vain kun mitattu on USKOTTAVASTI standardi: 219mm betoniseinä
        # EI ole 200mm — pakotettu snap veisi pinnan 9.5mm pieleen (>1.5mm
        # toleranssi). Kaukana standardista mitattu arvo on toimitusarvo.
        if abs(snapped - measured) > _STD_SNAP_TOL:
            snapped = measured
        updates = {"measured_thickness": measured, "thickness": snapped}
        delta = snapped - w.thickness
        if abs(delta) >= 0.5 and len(w.axis) >= 2 and len(pts):
            p0 = np.array(w.axis[0], float)
            p1 = np.array(w.axis[1], float)
            L = float(np.linalg.norm(p1 - p0))
            if L >= 1.0:
                u = (p1 - p0) / L
                n = np.array([-u[1], u[0]])
                rel = pts[:, :2] - p0
                t = rel @ u
                perp = rel @ n
                zm = (pts[:, 2] > w.z_min + 200.0) & (pts[:, 2] < w.z_min + w.height - 200.0)
                band = zm & (t > 0) & (t < L) & (np.abs(perp) < w.thickness / 2.0 + 60.0)
                if band.sum() >= 100:
                    side_pos = int((perp[band] > 0).sum())
                    side_neg = int(band.sum()) - side_pos
                    face_sign = 1.0 if side_pos >= side_neg else -1.0
                    # pinta face_sign-puolella pysyy: akseli siirtyy poispäin siitä
                    shift = -face_sign * (delta / 2.0) * n
                    updates["axis"] = [
                        [round(p0[0] + shift[0], 2), round(p0[1] + shift[1], 2)],
                        [round(p1[0] + shift[0], 2), round(p1[1] + shift[1], 2)],
                    ]
        out.append(w.model_copy(update=updates))
    return out


class Pipeline:
    """Koko pistepilvi → malli -putki."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self._progress = progress or (lambda msg: log.info(msg))
        self._scanner_origins: list = []   # täytetään kerroskohtaisesti (E57)
        self._sem_labels = None            # PointNetin luokat (SemanticLabels|None)
        self._shelf_fronts: list = []      # hyllyksi mitatut (diagnostiikka)

    def run(self, input_path: Path | list[Path], output_dir: Path) -> StructuralModel:
        output_dir.mkdir(parents=True, exist_ok=True)

        if isinstance(input_path, list):
            paths = input_path
            if len(paths) == 1:
                self._progress(f"Ladataan: {paths[0].name}")
            else:
                self._progress(f"Ladataan {len(paths)} skannia ja yhdistetään…")
            cloud = self._load_many(paths)
            input_path = paths[0]
        else:
            self._progress(f"Ladataan: {input_path.name}")
            cloud = self._load(input_path)

        if self.config.auto_voxel:
            self.config.voxel_size = _auto_voxel(cloud)
            self._progress(f"  Auto-voxel: {self.config.voxel_size:.1f} mm")

        self._progress("Esikäsittely (downsample + kohinasuodatus)…")
        # 5mm downsample endpoint-tarkkuutta varten — tarkempi kuin detektiovoxel mutta nopea
        _REFINE_VOXEL = 5.0
        refine_cloud = cloud.voxel_down_sample(_REFINE_VOXEL) if len(cloud.points) > 200_000 else cloud
        cloud = self._preprocess(cloud)

        cloud = self._semantic_filter(cloud)

        self._progress(f"Seinädetektio ({self.config.detector})…")
        model = self._detect(cloud, input_path, refine_cloud=refine_cloud)
        self._measure_support(model, refine_cloud)

        self._progress("Tallennetaan JSON…")
        model.save(output_dir / "model.json")

        if self.config.export_ifc:
            self._progress("Kirjoitetaan IFC…")
            self._write_ifc(model, output_dir / "model.ifc")

        if self.config.export_dxf:
            self._progress("Kirjoitetaan DXF…")
            self._write_dxf(model, output_dir / "model.dxf")
        else:
            _drop_stale_dxf(output_dir, self._progress)

        self._progress("Kirjoitetaan debug-pilvi…")
        self._write_debug(model, output_dir / "debug.ply")

        self._progress(f"Valmis. {model.summary()}")
        return model

    def run_floors(self, paths: list[Path], output_dir: Path) -> list[StructuralModel]:
        """Kerrosjako-putki: lataa yhden kerroksen kerrallaan, ei muistirajoitusta."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Diagnostiikka: kerää kaikki vaihelokit jaettavaan raporttiin (ei
        # geometriaa) — pilottiasiakas ei voi jakaa skanneja, tämän voi.
        from scan2bim.core.qa.diagnostics import DiagnosticsLog
        diag = DiagnosticsLog()
        for p in paths:
            diag.add_input(p)
        _user_progress = self._progress

        def _tee(msg: str) -> None:
            diag.log(msg)
            _user_progress(msg)
        self._progress = _tee

        try:
            return self._run_floors_inner(paths, output_dir, diag)
        except Exception as e:
            diag.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            self._progress = _user_progress
            diag.write(output_dir / "diagnostics.txt")

    def _run_floors_inner(self, paths: list[Path], output_dir: Path, diag) -> list[StructuralModel]:
        self._progress(f"Skannaustiedostoja: {len(paths)}")
        self._progress("Havaitaan kerroksia Z-histogrammista…")

        from scan2bim.core.geometry.floor_splitter import detect_floors_from_files
        import math
        # Kerrosjako tarvitsee vain Z-jakauman → riittää ~4 hajautettua tiedostoa
        # (kattaa kerrokset), ei kaikkien lukua. Säästää I/O:ta isolla setillä.
        sample = max(1, math.ceil(len(paths) / 4))
        floors = detect_floors_from_files(paths, sample_step=sample)
        self._progress(f"Löydettiin {len(floors)} kerros(ta).")

        if self.config.auto_voxel:
            # Adaptiivinen voxel datasta: kevyt 20mm-otos ensimmäisen kerroksen
            # kaistasta (muistiturvallinen isollekin talolle) → _auto_voxel skaalaa
            # työpistemäärän mukaan. Pieni huone → 8mm (tarkempi), iso talo → 25mm.
            # (Aiemmin kovakoodattu 12mm harhaanjohtavalla "Auto-voxel"-tekstillä.)
            try:
                from scan2bim.core.geometry.streaming import load_floor_slice as _probe_lfs
                _z_lo0, _z_hi0 = floors[0]
                _probe = _probe_lfs(paths, _z_lo0, _z_hi0, voxel_size=20.0, progress_cb=None)
                if len(_probe.points) >= 500:
                    self.config.voxel_size = _auto_voxel(_probe)
                else:
                    self.config.voxel_size = 12.0
            except Exception:
                self.config.voxel_size = 12.0
            self._progress(f"  Auto-voxel: {self.config.voxel_size:.1f} mm")

        source = paths[0]
        models: list[StructuralModel] = []
        _drop_stale_floors(output_dir, len(floors), self._progress)

        for floor_idx, (z_lo, z_hi) in enumerate(floors):
            self._progress(
                f"Kerros {floor_idx + 1}/{len(floors)}  "
                f"(Z {z_lo/1000:.2f}–{z_hi/1000:.2f} m)…"
            )

            from scan2bim.core.geometry.streaming import load_floor_slice, check_scan_consistency
            _samples: list = []
            cloud = load_floor_slice(
                paths, z_lo, z_hi,
                voxel_size=self.config.voxel_size,
                progress_cb=self._progress,
                icp_refine=self.config.icp_refine,
                sample_out=_samples if len(paths) > 1 else None,
            )
            if len(paths) > 1:
                _bad = check_scan_consistency(_samples)
                if _bad:
                    self._progress(
                        f"  VAROITUS: {len(_bad)} skannia ei jaa pintoja muiden kanssa "
                        f"({', '.join(_bad[:3])}{'…' if len(_bad) > 3 else ''}) — "
                        "eri kohteita samassa ajossa? Aja ne erikseen; tulos on epäluotettava."
                    )

            if len(cloud.points) < 500:
                self._progress(f"  Liian vähän pisteitä ({len(cloud.points)}), ohitetaan.")
                continue

            # Kohinasuodatus aina: voxelointi ei poista harhapisteitä, ja ne
            # sotkevat seinien koordinaatit + tuottavat valehavaintoja. Tarkkuus > nopeus.
            self._progress(f"  Pisteitä: {len(cloud.points):,} — kohinasuodatus…")
            cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)

            # Sanity: jos pilvi hajoaa useaan erilliseen XY-alueeseen, syötteet
            # eivät limity — todennäköisesti eri kohteiden skannauksia samassa
            # ajossa (esim. 10 eri asuntoa) → tulos olisi roskaa.
            n_regions = _count_disjoint_regions(cloud)
            if n_regions > 1:
                self._progress(
                    f"  VAROITUS: pistepilvi hajoaa {n_regions} erilliseen alueeseen. "
                    "Skannit eivät limity keskenään — jos ne ovat eri kohteita, "
                    "aja ne erikseen. Tulos voi olla epäluotettava."
                )

            from scan2bim.core.geometry.loader import scanner_origins
            origins: list = []
            for p in paths:
                for o in scanner_origins(p):
                    if z_lo <= float(o[2]) <= z_hi:
                        origins.append(o)
            self._scanner_origins = origins
            if origins:
                self._progress(f"  Skannerin origoja: {len(origins)} (okkluusiosuodatus päällä)")

            # Hieno keskikaista VAIN LOA-paksuusmittaukseen. Kaista = QA-mittarin
            # (_qa_band.py) resepti: ENSIMMÄISEN skannin RAA'AN z-alueen 35–65%
            # (lattia/katto/kalusteet pois). EI floor_splitterin padatun z_lo/z_hi:n
            # — se on leveämpi ja vie mittauksen eri korkeudelle → epäsuhta mittariin.
            from scan2bim.core.geometry.loader import (
                load_point_cloud as _lpc, ply_z_range, ply_autoscale_factor,
                e57_z_range, _e57_is_chunkable,
            )
            _zr = None
            _sfx = paths[0].suffix.lower()
            if _sfx == ".ply":
                # Iso PLY: z-alue lohkoluvulla, ei koko tiedostoa muistiin.
                _rng = ply_z_range(paths[0])
                if _rng is not None:
                    _sc = ply_autoscale_factor(paths[0])
                    _zr = (_rng[0] * _sc, _rng[1] * _sc)
            elif _sfx == ".e57" and _e57_is_chunkable(paths[0]):
                # Sama e57:lle — muuten koko tiedosto ladattaisiin pelkän
                # z-alueen takia, ennen kuin kaistalukua ehditään käyttää.
                _zr = e57_z_range(paths[0])
            if _zr is None:
                _z0 = np.asarray(_lpc(paths[0]).points)[:, 2]
                _zr = (float(_z0.min()), float(_z0.max()))
            _zmn, _zmx = _zr
            band_lo = _zmn + 0.35 * (_zmx - _zmn)
            band_hi = _zmn + 0.65 * (_zmx - _zmn)
            # Semanttinen suodatin ENSIN. thick_cloud ja refine_cloud eivät ole
            # sen syötettä — aiemmin ne ladattiin ennen suodatinta ja istuivat
            # (mitattu 0.8 GB) koko sen työjoukon päällä, joka on ison kohteen
            # muistihuippu. Suodatus myös pienentää cloudia ennen niiden latausta.
            self._progress(f"  Semanttinen suodatin ({len(cloud.points):,} pistettä)…")
            cloud = self._semantic_filter(cloud)

            self._progress("  Ladataan keskikaista paksuusmittaukseen (täysi resa)…")
            from scan2bim.core.geometry.streaming import load_floor_slice as _lfs
            # TÄYSI resa (voxel=0): voxelointi kvantisoi huippujen paikat → bias
            # (0mm→0.75mm mediaani, 1mm→1.8mm, 1.5mm→2.65mm). Raakapisteet pakolliset
            # ali-mm paksuuteen. Vain keskikaista (~30% korkeudesta) → muisti ok.
            # Kaista katolla 45 M pistettä — 159 M skannin 30 %-kaista on
            # 76 M täysresa (huippu 7 GB).
            # Satunnaisohennus (ei voxelointi) säilyttää piikin paikan → ali-mm
            # paksuus pysyy, muisti rajattu isollakin skannilla.
            thick_cloud = _lfs(
                paths, band_lo, band_hi, voxel_size=0.0, progress_cb=None,
                icp_refine=self.config.icp_refine, max_points=45_000_000,
            )
            # 5mm koko korkeuden pilvi pintalukitukseen/linjaukseen — detektiovoxelin
            # (12mm) sentroidi-bias siirtää pintamediaania useita mm (sama syy kuin
            # convert-polun refine_cloud). Katto 45 M: ison skannin 5mm-pilvi on
            # 100M+ (SLAM-kohina > 5mm) → satunnaisohennus rajaa muistin eikä
            # siirrä pintamediaania (toisin kuin karkeampi voxel).
            self._progress(
                f"  Ladataan 5mm-pilvi pintalukitukseen ({len(thick_cloud.points):,} "
                "keskikaistalla)…")
            refine_cloud = _lfs(
                paths, z_lo, z_hi, voxel_size=5.0, progress_cb=None,
                icp_refine=self.config.icp_refine, max_points=45_000_000,
            )

            self._progress(
                f"  5mm-pilvi {len(refine_cloud.points):,} pistettä")

            self._progress(f"  Seinädetektio ({self.config.detector})…")
            model = self._detect(cloud, source, refine_cloud=refine_cloud, thick_cloud=thick_cloud)
            model.metadata.floor_index = floor_idx
            model.metadata.floor_count = len(floors)
            self._measure_support(model, refine_cloud)

            floor_dir = output_dir / f"floor_{floor_idx:02d}"
            floor_dir.mkdir(exist_ok=True)
            model.save(floor_dir / "model.json")

            if self.config.export_ifc:
                self._progress("  Kirjoitetaan IFC…")
                self._write_ifc(model, floor_dir / "model.ifc")
                if self.config.export_qa:
                    try:
                        from scan2bim.core.qa.deviation import write_qa_report
                        # QA mittaa 5mm raakapilveä vasten (sama kuin pintalinjaus) —
                        # 12mm suodatettu voxel-pilvi piilotti 20mm+ pintavirheen
                        # (sentroidi-bias + PointNet vei osan pinnoista).
                        res = write_qa_report(
                            model, refine_cloud, floor_dir / "model.ifc",
                            floor_dir / "qa_report.txt", tol=self.config.qa_tolerance,
                        )
                        ov = res["deviation"].get("overall", {})
                        surf = res.get("surface")
                        if surf:
                            # Näytä MALLIN pintatarkkuus (oikea luku) — ei pistetason
                            # %-lukua joka on skannerin kohinan dominoima ja pelottaa turhaan.
                            self._progress(
                                f"  QA: pintatarkkuus mediaani {surf['median_mm']:.1f} mm "
                                f"({surf['n_ok']}/{surf['n_total']} seinää <=1.5 mm), "
                                f"{len(res['flags'])} tarkistettavaa "
                                f"| skannerikohina ~{surf['noise_rms_mm']:.0f} mm RMS"
                            )
                        else:
                            self._progress(
                                f"  QA: {ov.get('within_tol_pct', '?')} % <= {self.config.qa_tolerance} mm "
                                f"(pistetaso, sis. skannerikohinan), {len(res['flags'])} tarkistettavaa"
                            )
                    except Exception as e:
                        self._progress(f"  QA-raportti ohitettu: {e}")
            if self.config.export_dxf:
                self._write_dxf(model, floor_dir / "model.dxf")
            else:
                _drop_stale_dxf(floor_dir, self._progress)
            self._write_debug(model, floor_dir / "debug.ply")

            self._progress(f"  {model.summary()}")
            models.append(model)

        if models:
            if self.config.export_ifc and len(models) >= 1:
                from scan2bim.core.ifc.writer import write_building_ifc
                write_building_ifc(models, output_dir / "building.ifc", crs_epsg=self.config.crs_epsg)
                self._progress(f"Koko talo: {output_dir / 'building.ifc'}")
            self._progress(f"Valmis. {len(models)} kerrosta käsitelty.")
        return models

    # --- yksityiset vaiheet ---------------------------------------------------

    def _load(self, path: Path):
        from scan2bim.core.geometry.loader import load_point_cloud
        return load_point_cloud(path)

    def _load_many(self, paths: list[Path]):
        from scan2bim.core.geometry.loader import load_and_merge
        return load_and_merge(paths)

    def _preprocess(self, cloud):
        from scan2bim.core.geometry.preprocess import preprocess
        return preprocess(cloud, voxel_size=self.config.voxel_size)

    def _measure_support(self, model: StructuralModel, cloud) -> None:
        """Pintatuki raakapilvestä → valeseinät pois, loput Tarkistus-listalle."""
        try:
            from scan2bim.core.qa.deviation import measure_wall_support, flag_low_confidence
            from scan2bim.core.semantics.wall_semantics import (
                prune_unsupported_walls, snap_displaced_walls,
            )
            measure_wall_support(model, cloud)
            # Pinnaton seinä jolla ON jatkuva vastine = aito seinä väärässä
            # paikassa → siirretään, ei poisteta. Mitataan uudelleen korjatusta
            # sijainnista, jotta tarkistuslista näkee todellisen tilanteen.
            moved = snap_displaced_walls(model, cloud)
            if moved:
                worst = max(abs(s) for _, s in moved)
                self._progress(
                    f"  Siirretty {len(moved)} seinää mitatulle pinnalle "
                    f"(suurin {worst:.0f} mm)")
                measure_wall_support(model, cloud)
            dropped = prune_unsupported_walls(model, cloud)
            if dropped:
                self._progress(
                    f"  Poistettu {len(dropped)} seinää joilla ei ole yhtenäistä "
                    f"pintaa pilvessä (palkki-/pilarilinja)")
            # snap/close_open_corners venyttävät päitä pelkällä geometrisella
            # rajalla → seinä piirtyy evidenssin yli. Leikataan VASTA tässä:
            # nurkkavaiheet ajavat monta kierrosta, ja vain pilvi kertoo missä
            # pinta loppuu.
            from scan2bim.core.semantics.overstretch import trim_overstretched_walls
            cut = trim_overstretched_walls(model, cloud)
            if cut:
                measure_wall_support(model, cloud)
                worst = max(mm for _, mm in cut)
                self._progress(
                    f"  Leikattu {len(cut)} seinän irrallinen häntä evidenssiin "
                    f"(suurin {worst:.0f} mm)")
            # Kontuuri jäljittää vapaan tilan reunan → se näkee vain ENSIMMÄISEN
            # pinnan, ja puolen metrin päässä seisova kipsiseinä katoaa kokonaan.
            # VASTA tässä: aiemmat vaiheet (hyllynetupinta-poisto, dedup, snap)
            # pitävät rinnakkaista seinäparia virheenä ja söisivät molemmat.
            from scan2bim.core.semantics.second_face import find_hidden_walls
            hidden = find_hidden_walls(model.walls, cloud)
            if hidden:
                model.walls.extend(hidden)
                measure_wall_support(model, cloud)
                self._progress(
                    f"  Löydetty {len(hidden)} seinää toisen takaa (kontuurin katve)")
            left = [f for f in flag_low_confidence(model) if f["type"] == "wall"]
            if left:
                self._progress(f"  Tarkistettavaa: {len(left)} seinää")
        except Exception as e:
            self._progress(f"  Pintatuen mittaus ohitettu: {e}")

    def _semantic_filter(self, cloud):
        """Vaihe 2: poista kalusteet/krääsä ennen detektiota."""
        # Nollaa AINA ensin: labelit ovat kerros- ja pilvikohtaisia. Ilman tätä
        # edellisen kerroksen labelit jäisivät voimaan kun suodatin ei aja
        # (mode="off" tai geometrinen haara) ja detektori lukisi väärän kerroksen
        # luokkia oman ruudukkoavaimensa läpi.
        self._sem_labels = None
        self._shelf_fronts = []

        mode = self.config.semantic_filter_mode
        # Taaksepäinyhteensopivuus: vanha semantic_filter=True → "geometric"
        if mode == "off" and self.config.semantic_filter:
            mode = "geometric"
        # auto: PointNet vain liiketilassa (iso+korkea = lattia-katto-hyllyt).
        # Muualla off → ei regressiota (talo/asunto) eikä hidastumista.
        if mode == "auto":
            if _looks_like_retail(cloud):
                mode = "pointnet"
                self._progress("  Liiketila tunnistettu → semanttinen suodatin päälle")
            else:
                mode = "off"
        if mode == "off":
            return cloud

        n0 = len(cloud.points)
        if mode in ("pointnet", "pointnet-retail"):
            from scan2bim.core.segmentation.pointnet_filter import PointNetFilter  # noqa: PLC0415
            filt = PointNetFilter(model_path=self.config.semantic_model_path,
                                  variant="retail" if mode == "pointnet-retail" else "default")
            # Labelit talteen samalla inferenssillä: detektorin pystymaski voi
            # käyttää niitä eikä joudu päättelemään seinä/palkki-eroa uudestaan.
            out, self._sem_labels = filt.filter_with_labels(cloud)
            label = ("PointNet-liiketila" if mode == "pointnet-retail" else "PointNet")                 if filt.is_available() else "geometrinen (PointNet-fallback)"
        else:
            from scan2bim.core.segmentation.semantic_filter import SemanticFilter  # noqa: PLC0415
            out = SemanticFilter().filter(cloud)
            label = "geometrinen"

        self._progress(f"  Semanttinen suodatin ({label}): {n0} → {len(out.points)} pistettä "
                       f"({100*len(out.points)/max(n0,1):.0f}% rakenteellisia)")
        return out

    def _detect(self, cloud, source_path: Path, refine_cloud=None, thick_cloud=None) -> StructuralModel:
        import scan2bim.core.segmentation.wall_ransac  # noqa: F401
        import scan2bim.core.segmentation.wall_density  # noqa: F401
        import scan2bim.core.segmentation.wall_normals  # noqa: F401
        import scan2bim.core.segmentation.wall_contour  # noqa: F401
        import scan2bim.core.segmentation.wall_histogram  # noqa: F401
        import scan2bim.core.floorplan.detector  # noqa: F401
        from scan2bim.core.segmentation.base import DetectorRegistry
        from scan2bim.core.segmentation.slab_detector import detect_slabs

        from scan2bim.core.semantics.wall_semantics import filter_structural_walls, refine_thicknesses
        from scan2bim.core.semantics.corner_snap import snap_corners, close_open_corners

        # Rakennusvaippa-rajaus: poista katteeton ulkoalue (maasto/piha) ennen
        # kontuuria. No-op sisätiladatalle. refine_cloud/thick_cloud jäävät
        # rajaamatta → ulkoseinien paksuus mitataan silti niiden ulkopinnasta.
        cloud = _crop_to_building_envelope(cloud)

        # Liiketilassa (iso + korkea, suorakulmainen big-box) HISTOGRAMMI-detektori:
        # deterministinen, ~130× nopeampi ja pilarivapaa (ransac-tason kallistuma
        # nappaa pilarilinjoja). Asunnot/talot voivat olla ei-Manhattan (vinot
        # seinät) → niissä histogrammi löytää vähemmän → pidä configin detektori.
        is_retail = _looks_like_retail(cloud)
        is_large = _occupancy_area_m2(cloud) >= _LARGE_SPACE_M2
        detector_name = self.config.detector
        # Iso tila TAI liiketila → histogrammi (myös contour-oletuksesta): iso
        # rakennus jonka lattia on osin okkluusiossa jää contourilla vajaaksi
        # (vain skannerihuone). Asunto/talo (pieni pohja) pysyvät contourissa.
        if detector_name in ("ransac", "density", "contour") and (is_retail or is_large):
            detector_name = "histogram"
            why = "liiketila" if is_retail else "iso tila"
            self._progress(f"  {why} → histogrammi-detektori (deterministinen)")
        detector = DetectorRegistry.get(detector_name)()
        # Semanttiset labelit detektorille jos suodatin tuotti ne. Muut
        # detektorit eivät tunne kenttää → ei vaikutusta niihin.
        if self._sem_labels is not None and hasattr(detector, "semantic_labels"):
            detector.semantic_labels = self._sem_labels
        model = detector.detect(cloud)
        model.slabs = detect_slabs(cloud)

        floor_slab = next((s for s in model.slabs if s.slab_type == "floor"), None)

        # Pintalukitus tarvitsee mahd. tarkan pilven: 12mm-detektiovoxelin
        # sentroidi-bias siirtää yksipuolisen pinnan ~sisäänpäin. Hienompi
        # refine_cloud (5mm) → bias laskee mediaani ~13mm→~3mm.
        lock_cloud = refine_cloud if refine_cloud is not None else cloud

        model.walls = filter_structural_walls(model.walls, model.slabs)
        model.walls = refine_thicknesses(model.walls, lock_cloud)
        model.walls = _recenter_wall_axes(model.walls, lock_cloud)

        # Huonealan kontuurit (KAIKKI erilliset alueet, ei vain suurin — paksun
        # seinän takainen huone on oma polygoninsa) → perimetriseinien lähde.
        # Lasketaan VASTA seinien suodatuksen jälkeen: seinät toimivat alueen
        # katkaisijoina, joten niiden pitää olla puhdas joukko.
        floor_contours: list = []
        if floor_slab is not None:
            from scan2bim.core.segmentation.slab_detector import detect_floor_contours
            # Katto mukaan: siinä ei ole kalusteita → huoneala jää kiinteäksi eikä
            # kontuuri kierrä keilausvarjojen lahtia (rikkoi rajan itsensä leikkaavaksi).
            ceil_slab = next((s for s in model.slabs if s.slab_type == "ceiling"), None)
            floor_contours = detect_floor_contours(
                cloud, floor_slab.elevation,
                ceiling_elevation=ceil_slab.elevation if ceil_slab is not None else None,
                walls=model.walls,
            )
            if not floor_contours:
                floor_contours = [floor_slab.boundary]
            _areas = sorted(
                (abs(float(np.dot(np.asarray(b, float)[:, 0],
                                  np.roll(np.asarray(b, float)[:, 1], -1))
                          - np.dot(np.asarray(b, float)[:, 1],
                                   np.roll(np.asarray(b, float)[:, 0], -1)))) / 2e6
                 for b in floor_contours if len(b) >= 3), reverse=True)
            self._progress(
                f"  Lattiakontuureja: {len(floor_contours)} "
                f"(alat {', '.join(f'{a:.0f}' for a in _areas[:5])} m²)")

        # Toinen deduplikointi: akselinkorjaus saattaa tuoda aiemmin eri paikassa olevia
        # seiniä samalle akselille (kuten wall_105/wall_108 jotka ovat saman seinän pinnat)
        # Täydennä perimetri lattian ulkorajasta — sulkee ulkoseinät joita
        # detektori ei nappaa (keilausvarjot/ikkunat/kalusteet).
        if floor_contours:
            floor_z_w = min((w.z_min for w in model.walls), default=0.0)
            wall_h = max((w.height for w in model.walls), default=2700.0)
            from scan2bim.core.semantics.perimeter import add_perimeter_walls
            # add_perimeter_walls siirtää akselin ulospäin thickness/2 → sisäpinta
            # osuu lattiakontuuriin. Tarkennetaan vielä todelliseen sisäpintaan:
            # keep_thickness säilyttää 300mm-paksuuden eikä nappaa naapuriseinää.
            perim: list = []
            for boundary in floor_contours:
                perim += add_perimeter_walls(
                    boundary, model.walls + perim, floor_z_w, wall_h,
                    pts=np.asarray(cloud.points),
                )
            # add_perimeter_walls numeroi id:t polygonikohtaisesti alusta →
            # uniikit id:t koko joukolle (QA/IFC sekoaa duplikaateista)
            perim = [w.model_copy(update={"id": f"wall_ext_{i:03d}"}) for i, w in enumerate(perim)]
            perim = _recenter_wall_axes(perim, lock_cloud, band=300.0, keep_thickness=True)
            model.walls = model.walls + perim

        from scan2bim.core.semantics.wall_semantics import _deduplicate
        model.walls = _deduplicate(model.walls)

        # Suorista seinät kahteen kohtisuoraan suuntaan ennen kulmien yhdistämistä —
        # vinot seinät eivät muuten kohtaa puhtaasti eivätkä huoneet sulkeudu.
        from scan2bim.core.semantics.orthogonal import regularize_orthogonal, fine_rotate_walls
        model.walls = regularize_orthogonal(model.walls)

        # Per-seinä hienokierto: globaali akseli on usein 1–2° vinossa todelliseen
        # ruudukkoon → pitkän seinän pää ajautuu 100–200 mm. Kierrä riittävän pitkät
        # seinät (±2.5°) parhaiten omiin pisteisiinsä. Tehdään ennen nurkkien
        # snäppäystä jotta snap reconnektoi päät kierron jälkeen.
        if model.walls:
            lz = min((w.z_min for w in model.walls), default=0.0)
            lh = max((w.height for w in model.walls), default=2700.0)
            fr_pts = np.asarray(lock_cloud.points)
            model.walls = fine_rotate_walls(
                model.walls, fr_pts, z_min=lz + 200.0, z_max=lz + lh - 200.0
            )
            # Hienokierto voi tehdä lähes päällekkäisistä seinistä (perimetri +
            # detektoitu samalla linjalla) hieman ei-yhdensuuntaisia → ne eivät
            # enää sulaudu ja rajaavat ohuen valehuoneen. Dedup uudestaan kierron
            # jälkeen poistaa parit ennen nurkkien snäppäystä.
            model.walls = _deduplicate(model.walls)

        model.walls = snap_corners(model.walls)
        trim_cloud = refine_cloud if refine_cloud is not None else cloud
        model.walls = _trim_wall_endpoints(model.walls, trim_cloud)
        model.walls = snap_corners(model.walls)  # reconnektoi trim:in katkaisevat nurkat

        # Poista irralliset tynkäseinät (pää ilmassa, ei rajaa huonetta)
        from scan2bim.core.semantics.wall_semantics import remove_dangling_walls
        model.walls = remove_dangling_walls(model.walls)

        # Poista seinät jotka ovat kaukana KAIKISTA skannereista (harvan reunapilven
        # ajautuma-artefaktit). No-op ilman skannerisijainteja (synteettinen/E57:tön).
        # ISOSSA TILASSA OHITETAAN: 12 m -raja on asuntomittakaavan vakio; iso
        # rakennus jonka skannerit ovat yhdessä huoneessa jättää aidot vaippaseinät
        # >12 m päähän → mitattu Matterport-aula: raja poisti 19 m conf=1.00 -seinän
        # (koko vasen perimetri) + 2 perimetripätkää, kaikki aitoja (residuaali vision).
        # Histogrammi (ison tilan detektori) on rakenteellisesti puhdas → ei funny-
        # seiniä joita raja torjuisi, joten poisto olisi pelkkää haittaa.
        if not is_large:
            from scan2bim.core.semantics.wall_semantics import remove_walls_beyond_scan_range
            _nw = len(model.walls)
            model.walls = remove_walls_beyond_scan_range(model.walls, self._scanner_origins)
            if len(model.walls) < _nw:
                self._progress(f"  Skannausalueen ulkopuolisia seiniä poistettu: {_nw - len(model.walls)}")

        # LUKITSE PINNAT LOPULLISESTI: snap/trim siirtävät päätepisteitä ja kumoavat
        # aiemman pintalukituksen (akseli jää pistepinnalle → mallin pinta thickness/2
        # ohi → bias ~50mm). Aja surface_lock vielä kerran, sitten snap nurkat kiinni.
        model.walls = _recenter_wall_axes(model.walls, lock_cloud)
        model.walls = snap_corners(model.walls)
        # Hienokierto voi tehdä seinistä hieman ei-yhdensuuntaisia → snap jatkaa
        # niitä kaukaisiin risteyksiin (ylityspätkä tyhjään tilaan → ylimääräinen
        # huone). Trimmaa päät takaisin todelliseen dataan, snap reconnektoi nurkat.
        model.walls = _trim_wall_endpoints(model.walls, trim_cloud)
        model.walls = snap_corners(model.walls)

        # Vinojen (ei-Manhattan) seinien kulman viimeistely täysipitkällä akselilla:
        # ensimmäinen hienokierto ajoi ennen snappia lyhyellä detektiopätkällä →
        # kulma jäi vajaaksi. Koskee vain grid-linjasta poikkeavia seiniä.
        if model.walls:
            from scan2bim.core.semantics.orthogonal import refine_skew_walls
            lz2 = min((w.z_min for w in model.walls), default=0.0)
            lh2 = max((w.height for w in model.walls), default=2700.0)
            _pre = [tuple(map(tuple, w.axis)) for w in model.walls]
            model.walls = refine_skew_walls(
                model.walls, np.asarray(lock_cloud.points),
                z_min=lz2 + 200.0, z_max=lz2 + lh2 - 200.0,
            )
            if _pre != [tuple(map(tuple, w.axis)) for w in model.walls]:
                model.walls = snap_corners(model.walls)

        # LOA-TARKKA PAKSUUS: mittaa kaksipuolisten seinien paksuus täysiresan
        # raakapisteistä ali-bin tarkkuudella ja keskitä akseli pintojen väliin.
        # _surface_lock asettaa karkean paksuuden (12mm-voxel ~33mm virhe); tämä
        # raakapistemittaus vie kaksipuolisen seinän paksuusvirheen <1.5mm.
        # Yksipuoliset jätetään ennalleen (ei mitattavissa). Snap pitää nurkat.
        if thick_cloud is not None and len(np.asarray(thick_cloud.points)) > 0:
            _before = [(w.thickness, tuple(map(tuple, w.axis))) for w in model.walls]
            _ceil_z = next(
                (s.elevation for s in model.slabs if s.slab_type == "ceiling"), None)
            model.walls = _thickness_lock_walls(
                model.walls, thick_cloud,
                ceiling_xy=_ceiling_band_xy(lock_cloud, _ceil_z),
            )
            _nch = sum(
                1 for (t0, a0), w in zip(_before, model.walls)
                if abs(w.thickness - t0) > 0.2 or tuple(map(tuple, w.axis)) != a0
            )
            self._progress(f"  Pintalukitus: {_nch}/{len(model.walls)} seinää tarkennettu raakapisteistä")
            model.walls = snap_corners(model.walls)
        # HUOM: standardipaksuus-snäppäys kokeiltu ja HYLÄTTY — raakapistemittaus on
        # jo tarkka (2.6mm), snäppäys siirsi paksuudet vääriin standardeihin (6.0mm).
        # Todelliset paksuudet eivät ole oletettuja vakioita; luota mittaukseen.

        # LOPULLINEN DEDUP: kaikki akselinsiirrot (recenter/snap/trim/thickness_lock)
        # on nyt tehty → lähekkäiset duplikaatit (esim. perimetri ext_003 77mm +
        # ext_004 266mm = sama yläseinä) ovat vasta NYT lopullisilla, päällekkäisillä
        # paikoillaan. Aiemmat dedupit eivät napanneet niitä koska sijainnit muuttuivat
        # vielä. Tehdään ennen huone/aukko-detektiota jotta ne käyttävät puhdasta joukkoa.
        from scan2bim.core.semantics.wall_semantics import bridge_lintel_gaps, merge_collinear_walls
        model.walls = merge_collinear_walls(model.walls)   # yhdistä sama seinä jaettuna (poistaa pöhö-pätkät)
        model.walls = _deduplicate(model.walls)
        # Silloita oviaukkojen katkaisemat seinät (railo + ylitysevidenssi) —
        # ovi kollineaaristen pätkien VÄLISSÄ ei muuten löydy koskaan.
        model.walls = bridge_lintel_gaps(model.walls, np.asarray(lock_cloud.points))
        model.walls = snap_corners(model.walls)
        # Sulje vajaat perimetrinurkat: yhdistä avoimet päät PAREITTAIN (vain avoimet
        # päät, vain toisiinsa) → ei gridiä kuten iso _resolve_corners-extend tekisi.
        model.walls = close_open_corners(model.walls)

        # Trim/snap voi romahduttaa datattoman seinän pisteeksi tai lyhyeksi
        # jämäksi — nollamittainen "seinä" IFC:ssä on roskaa.
        _MIN_FINAL_WALL = 300.0
        model.walls = [
            w for w in model.walls
            if len(w.axis) >= 2
            and float(np.hypot(w.axis[1][0] - w.axis[0][0], w.axis[1][1] - w.axis[0][1])) >= _MIN_FINAL_WALL
        ]

        # TOIMITUSPAKSUUS ennen lopullista pintalinjausta: snäppäys ei saa enää
        # liikuttaa linjattua pintaa (avaisi nurkat ±(snap-mitattu)/2).
        model.walls = _snap_delivery_thickness(model.walls, cloud)

        # LOPULLINEN PINTALINJAUS: merge/snap/close-ketju liikutti linjoja
        # (T-liitosprojektio vetää päätepisteen naapurin linjalle → seinä
        # kallistuu ~5mm). Linjaa TOIMITUSPINTA pistepinnan MEDIAANIIN koko
        # korkeudelta (sama estimaattori kuin QA — huippu ja mediaani eroavat
        # kallellaan olevalla seinällä) ja sulje nurkat linjoja säilyttäen:
        # päät liikkuvat vain oman akselin suunnassa linja-linja-leikkauksiin.
        model.walls = _align_faces_to_surface_median(model.walls, lock_cloud)
        model.walls = snap_corners(model.walls, preserve_lines=True)

        # Normalisoi seinien korkeus lattia-katto-välille (tarkka arkkitehtimalli)
        floor_z = min(
            (s.elevation for s in model.slabs if s.slab_type == "floor"),
            default=float(min((w.z_min for w in model.walls), default=0.0)),
        )
        ceiling_z = max(
            (s.elevation for s in model.slabs if s.slab_type == "ceiling"),
            default=float(max((w.z_min + w.height for w in model.walls), default=floor_z + 2700.0)),
        )
        room_height = round(ceiling_z - floor_z, 1)
        if room_height > 500.0:
            model.walls = [
                w.model_copy(update={"z_min": round(floor_z, 1), "height": room_height})
                for w in model.walls
            ]

        # Poista lattia-katto-hyllykön etupintaan syntyneet valeseinät: hyllyn
        # etupinta on geometrisesti seinä (lattiasta kattoon) mutta seisoo
        # ~500-1200 mm perimetrin SISÄLLÄ rinnakkain sen kanssa. Semanttinen
        # suodatin ei sitä poista (tiheä pystytaso). Ennen huonepolygonia jotta
        # tilat lasketaan puhtaasta seinäjoukosta.
        from scan2bim.core.semantics.wall_semantics import remove_shelf_front_walls
        _pre_shelf = list(model.walls)
        model.walls = remove_shelf_front_walls(model.walls, retail=is_retail)
        # Muista poistetut: `data/_shelf_gt_probe.py` mittaa niiden GT-luokan,
        # eli näkeekö sääntö hyllyjä vai aitoja seiniä.
        _kept = {w.id for w in model.walls}
        self._shelf_fronts = [w for w in _pre_shelf if w.id not in _kept]
        if self._shelf_fronts:
            self._progress(
                f"  Hyllyn etupinta-valeseiniä poistettu: {len(self._shelf_fronts)}")

        # Korvaa laatan rajapisteet seinien leikkauspisteistä johdetulla polygonilla
        from scan2bim.core.semantics.room_polygon import build_room_polygon, snap_walls_to_polygon
        room_poly = build_room_polygon(model.walls)
        if room_poly and len(room_poly) >= 3:
            model.slabs = [s.model_copy(update={"boundary": room_poly}) for s in model.slabs]

        self._progress(f"  Seinien viimeistely valmis ({len(model.walls)} seinää) — "
                       "tilat, aukot, pilarit, palkit…")
        from scan2bim.core.semantics.room_detector import detect_rooms
        model.spaces = detect_rooms(model.walls, floor_z, ceiling_z,
                                    boundaries=floor_contours)

        from scan2bim.core.segmentation.opening_detector import detect_openings, reclassify_interior_windows
        model.openings = detect_openings(model.walls, cloud, floor_z, scanner_origins=self._scanner_origins)
        # Ikkuna vaatii ulkoseinän: sisäseinän (huone molemmin puolin) leveä aukko → ovi.
        model.openings = reclassify_interior_windows(model.walls, model.spaces, model.openings)

        # Kuvaohjatut aukot: E57:n skannerikuvista LÄPINÄKYVYYS-signaalilla (säde näkee
        # seinätason ohi = ikkuna/ovi). VAIN lisää aukkoja joita geometria ei löytänyt.
        # No-op ilman E57-kuvia → PLY/asunto/talo/retail muuttumaton (gauntlet-turva).
        if source_path.suffix.lower() == ".e57":
            try:
                from scan2bim.core.segmentation.image_openings import detect_image_openings
                _img_ops = detect_image_openings(model.walls, source_path, np.asarray(cloud.points))
                _added = 0
                for _io in _img_ops:
                    _dup = any(_io.wall_id == o.wall_id
                               and abs(_io.position_along - o.position_along) < max(o.width, _io.width)
                               for o in model.openings)
                    if not _dup:
                        model.openings.append(_io); _added += 1
                if _added:
                    self._progress(f"  Kuvaohjattuja aukkoja lisätty: {_added}")
            except Exception as _e:  # noqa: BLE001
                self._progress(f"  Kuva-aukot ohitettu: {_e}")

        from scan2bim.core.segmentation.column_detector import detect_columns
        model.columns = detect_columns(cloud, model.walls, floor_z, ceiling_z)

        from scan2bim.core.segmentation.beam_detector import detect_beams
        # Soffit-rajaus vain jos AITO kattolaatta löytyi (valmis tila) — työmaalla
        # ceiling_z on seinänlakivarasija eikä rajausta saa tehdä (katkoisi palkit).
        _has_ceiling = any(s.slab_type == "ceiling" for s in model.slabs)
        model.beams = detect_beams(cloud, model.walls, floor_z, ceiling_z,
                                   has_ceiling=_has_ceiling)

        model.metadata.source_file = source_path.name
        model.metadata.voxel_size = self.config.voxel_size
        return model

    def _write_ifc(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.ifc.writer import write_ifc
        write_ifc(model, path, crs_epsg=self.config.crs_epsg)

    def _write_dxf(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.export.dxf import write_dxf
        write_dxf(model, path)

    def _write_debug(self, model: StructuralModel, path: Path) -> None:
        from scan2bim.core.export.debug_cloud import write_debug_cloud
        floor_z = min(
            (s.elevation for s in model.slabs if s.slab_type == "floor"),
            default=float(min((w.z_min for w in model.walls), default=0.0)),
        )
        write_debug_cloud(model, path, floor_z, z_offset=0.0)

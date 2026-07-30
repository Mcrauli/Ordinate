"""
Cloud2BIM-tyylinen ääriviivapohjainen seinädetektio.

Toisin kuin normals/Hough (joka löytää erilliset seinäpinnat ja parittaa ne),
tämä menetelmä lähtee seinämassan ulkoreunasta → tuottaa jatkuvia, yhtenäisiä
seiniä jotka muodostavat suljettuja huoneita.

Algoritmin lähde ja lisenssi
----------------------------
Vaiheet 1–7 on portattu Cloud2BIM-projektista
(``reference/Cloud2BIM/aux_functions.py::identify_walls``).

    Cloud2BIM — MIT License, Copyright (c) 2025 Václav Nežerka
    https://github.com/vnezerka/Cloud2BIM

MIT edellyttää copyright-ilmoituksen säilyttämistä johdannaisissa; koko
lisenssiteksti on ``THIRD-PARTY-NOTICES.md``-tiedostossa ja se toimitetaan
sovelluksen mukana.

Algoritmi (portattu reference/Cloud2BIM/aux_functions.py::identify_walls):
  1. Vaaka-z-kaista 0.85–1.2 storey-korkeudesta → 2D-pisteet
  2. 2D-tiheyshistogrammi → binäärimaski (tiheyskynnys)
  3. Morfologinen closing (5x5) → täyttää pienet reiät
  4. cv2.findContours(RETR_EXTERNAL, CHAIN_APPROX_NONE) → seinämassan ääriviivat
  5. Douglas-Peucker → suorat segmentit, lyhyet pois
  6. merge_collinear_segments → yhdistä samalla suoralla olevat
  7. group_segments → parittaa vastakkaiset rinnakkaispinnat → seinä
     (akseli = keskiviiva, paksuus = pintojen kohtisuora etäisyys)
  8. ryhmittymättömät ulkopinnat → fasadiseinät (perimetri-swell)
"""
from __future__ import annotations

import math

import cv2
import numpy as np
import open3d as o3d

from scan2bim.schemas.model import ElementSource, Metadata, StructuralModel, Wall

from .base import DetectorRegistry, ElementDetector

# --- parametrit (mm) -------------------------------------------------------
_PIXEL_SIZE = 30.0          # mm/pikseli rasterille (Cloud2BIM: resolution*grid_coeff)
_CLOSE_KERNEL = 5           # morfologisen closingin ydin (pikseliä)
_DP_TOL = 40.0              # mm — Douglas-Peucker -toleranssi
_MIN_WALL_LENGTH = 500.0    # mm — lyhyemmät segmentit pois
_MIN_THICKNESS = 60.0       # mm
_MAX_THICKNESS = 350.0      # mm
_ANGLE_TOL_DEG = 6.0        # rinnakkaisuuden kulmatoleranssi
# Kaista lattia–katto-välistä: keskialueella huoneet ovat tyhjää ilmaa ja vain
# seinillä (ja kalusteilla) on pisteitä → seinät erottuvat ohuina viivoina.
# (Cloud2BIM käyttää 0.85–1.2 storey-korkeudesta MONIKERROS-pinoon; yksittäiselle
# kaappaukselle keskikaista antaa tyhjät huoneet eikä kattolaattaa.)
_Z_BAND = (0.35, 0.65)      # osuus lattia–katto-korkeudesta
_DENSITY_THRESHOLD = 8      # min pistettä per pikseli → maski päälle
_DEFAULT_THICKNESS = 200.0  # mm — siemen ohuelle (parittomalle) seinälle; pipeline mittaa todellisen

# Monikerros-pystymaski (kalustesuodatus). Seinä ulottuu lattiasta kattoon → se on
# "täynnä" lähes kaikissa vaakaviipaleissa; kaluste (kaappi, sänky, pöytä, jääkaappi)
# on osakorkuinen → täynnä vain osassa viipaleita. Pidetään vain pikselit jotka
# täyttyvät vähintään _VSLICE_FRAC osuudessa viipaleita.
_VSLICE_STEP    = 150.0     # mm — vaakaviipaleen paksuus
_VSLICE_BOTTOM  = 350.0     # mm — aloita näin korkealta lattiasta (lattiakrääsä/jalkalistat pois)
_VSLICE_TOP     = 250.0     # mm — lopeta näin matalalta katosta (valaisimet/IV-putket pois)
_VSLICE_FRAC    = 0.55      # osuus viipaleista joissa pikselin oltava täynnä → seinä
_VSLICE_MIN_PER = 2         # min pistettä pikselissä per viipale → viipale "täynnä"
# KORKEA TILA: osuussääntö olettaa että seinä ulottuu lattiasta kattoon. Palkitetussa
# rungossa se ei ulotu — seinä päättyy palkin alapintaan metrejä katon alle, ja
# 0.55 × 10.3 m = 5.4 m jatkuvuutta on enemmän kuin korkein seinä. Mitattu Rohbau3D
# site_07:llä (GT-labelit): aidon seinäpikselin jatkuvuus mediaani 1.35 m → 0 seinää.
# Siksi korkeassa tilassa riittää ABSOLUUTTINEN yhtäjaksoinen pystyjakso. Mitattu
# läpäisy jaksolla ≥1500 mm: Wall/Drywall 47.7 %, Column 35.0 %, Beam 2.0 %, TGA 0.0 %.
_VSLICE_RUN_MM  = 1500.0    # mm — riittävä yhtäjaksoinen pystyjakso korkeassa tilassa
_VSLICE_TALL_MM = 4000.0    # mm — tätä korkeammassa tilassa osuussääntö ei päde
# Kun semanttiset labelit ovat käytettävissä, geometria saa olla vähemmän
# varovainen: palkkien torjunta ei ole enää pelkän pystyjatkuvuuden varassa.
# Mitattu Rohbau3D-GT:llä (seinäpikselit / palkkikontaminaatio):
#   jakso ≥1500 mm koko pilvestä      47.7 % / 2.0 %   (nykyinen)
#   jakso ≥1000 mm koko pilvestä      65.6 % / 6.0 %
#   jakso ≥1000 mm VAIN seinäluokasta 65.3 % / 2.6 %   ← tämä
_VSLICE_RUN_SEM_MM = 1000.0  # mm — löysempi jakso kun luokka on tiedossa

_MAX_WORK_POINTS = 1_200_000  # raskas detektori → ajetaan harvennetulle pilvelle


# ---------------------------------------------------------------------------
# Geometriapikkufunktiot (portattu Cloud2BIM)
# ---------------------------------------------------------------------------

def _floor_ceiling(z: np.ndarray, z_min: float, z_max: float) -> tuple[float, float]:
    """Lattia + katto z-tiheyshistogrammin reunimmaisista vahvoista piikeistä."""
    hist, edges = np.histogram(z, bins=200)
    centers = 0.5 * (edges[:-1] + edges[1:])
    thr = 0.25 * float(hist.max())
    strong = np.where(hist >= thr)[0]
    if len(strong) < 2:
        return z_min, z_max
    floor_z = float(centers[strong[0]])
    ceil_z = float(centers[strong[-1]])
    if ceil_z - floor_z < 1500.0:  # epäuskottava → koko alue
        return z_min, z_max
    return floor_z, ceil_z


def _dist(p1, p2) -> float:
    return float(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))


def _point_to_line(point, a, b) -> float:
    a = np.asarray(a, float); b = np.asarray(b, float); p = np.asarray(point, float)
    ab = b - a
    L = np.linalg.norm(ab)
    if L < 1e-9:
        return float(np.linalg.norm(p - a))
    ab /= L
    proj = np.dot(p - a, ab)
    closest = a + proj * ab
    return float(np.linalg.norm(p - closest))


def _seg_angle(seg1, seg2) -> float:
    dx1, dy1 = seg1[1][0] - seg1[0][0], seg1[1][1] - seg1[0][1]
    dx2, dy2 = seg2[1][0] - seg2[0][0], seg2[1][1] - seg2[0][1]
    m1 = math.hypot(dx1, dy1); m2 = math.hypot(dx2, dy2)
    if m1 * m2 == 0:
        return 90.0
    c = (dx1 * dx2 + dy1 * dy2) / (m1 * m2)
    return math.degrees(math.acos(min(1.0, max(-1.0, c))))


def _is_parallel(seg1, seg2, tol=_ANGLE_TOL_DEG) -> bool:
    a = _seg_angle(seg1, seg2)
    return a < tol or abs(a - 180.0) < tol


def _find_furthest(points):
    best = -1.0; s = e = points[0]
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            d = _dist(points[i], points[j])
            if d > best:
                best, s, e = d, points[i], points[j]
    return s, e


def _collinear(seg1, seg2, min_thick, max_dist) -> bool:
    close = any(_dist(p1, p2) <= max_dist for p1 in seg1 for p2 in seg2)
    colin = any(_point_to_line(p, seg1[0], seg1[1]) < (min_thick / 2) for p in seg2)
    return close and colin


def _merge_collinear(segments, min_thick, max_dist):
    final = []
    segs = [list(s) for s in segments]
    while segs:
        base = segs[0]
        to_merge = [base]
        for other in segs[1:]:
            if _collinear(base, other, min_thick, max_dist) and _is_parallel(base, other, tol=3.0):
                to_merge.append(other)
        if len(to_merge) > 1:
            all_pts = [pt for seg in to_merge for pt in seg]
            s, e = _find_furthest(all_pts)
            segs.append([s, e])
        else:
            final.append(base)
        for seg in to_merge:
            segs.remove(seg)
    return final


def _overlap_parallel(seg1, seg2, min_overlap) -> bool:
    ang = math.atan2(seg1[1][1] - seg1[0][1], seg1[1][0] - seg1[0][0])
    cos, sin = math.cos(-ang), math.sin(-ang)

    def rot(p):
        return (cos * p[0] - sin * p[1], sin * p[0] + cos * p[1])

    r1 = [rot(seg1[0]), rot(seg1[1])]
    r2 = [rot(seg2[0]), rot(seg2[1])]
    x1a, x1b = sorted([r1[0][0], r1[1][0]])
    x2a, x2b = sorted([r2[0][0], r2[1][0]])
    start = max(x1a, x2a); end = min(x1b, x2b)
    return (end - start) > min_overlap if start < end else False


def _perp_dist(seg1, seg2) -> float:
    if _is_parallel(seg1, seg2):
        return _point_to_line(seg2[0], seg1[0], seg1[1])
    return float("inf")


def _group_segments(segments, max_thick, angle_tol=_ANGLE_TOL_DEG):
    """Parittaa vastakkaiset rinnakkaispinnat (pari = seinä). Loput = fasadiehdokkaat."""
    grouped = []
    facade = []
    segs = list(segments)
    while segs:
        cur = segs.pop(0)
        group = [cur]
        i = 0
        while i < len(segs):
            s = segs[i]
            if (
                _is_parallel(cur, s, angle_tol)
                and any(_dist(p1, p2) <= max_thick for p1 in cur for p2 in s)
                and _overlap_parallel(cur, s, min_overlap=max_thick)
            ):
                group.append(s)
                segs.pop(i)
            else:
                i += 1
        if len(group) >= 2:
            grouped.append(group)
        else:
            facade.append(cur)
    return grouped, facade


def _wall_axis(group):
    """Akseli rinnakkaisparille: keskiviiva, paksuus = pintojen etäisyys."""
    lengths = [_dist(s[0], s[1]) for s in group]
    longer = group[int(np.argmax(lengths))]
    shorter = group[1 - int(np.argmax(lengths))] if len(group) == 2 else group[
        int(np.argsort(lengths)[-2])]

    d = [longer[1][0] - longer[0][0], longer[1][1] - longer[0][1]]
    norm = math.hypot(d[0], d[1])
    if norm < 1e-9:
        return None
    d = [d[0] / norm, d[1] / norm]

    mean_dist = float(np.mean([_perp_dist(longer, shorter), _perp_dist(shorter, longer)]))
    if not math.isfinite(mean_dist):
        return None
    half = mean_dist / 2.0

    a_s = [longer[0][0] - half * d[1], longer[0][1] + half * d[0]]
    a_e = [longer[1][0] - half * d[1], longer[1][1] + half * d[0]]
    s_init = sum(_dist(p, a_s) + _dist(p, a_e) for p in longer + shorter)

    b_s = [longer[0][0] + half * d[1], longer[0][1] - half * d[0]]
    b_e = [longer[1][0] + half * d[1], longer[1][1] - half * d[0]]
    s_flip = sum(_dist(p, b_s) + _dist(p, b_e) for p in longer + shorter)

    if s_flip < s_init:
        a_s, a_e = b_s, b_e
    return [a_s, a_e], mean_dist


def _dominant_angle(axes) -> float:
    """Pituuspainotettu dominantti suunta (rad), mod 90° → ortogonaalirunko."""
    sx = sy = 0.0
    for a_s, a_e, _ in axes:
        dx = a_e[0] - a_s[0]; dy = a_e[1] - a_s[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        ang = math.atan2(dy, dx)
        # 4× kulma → 0/90/180/270 kuvautuvat samaan → keskiarvoistus mod 90°
        sx += L * math.cos(4 * ang)
        sy += L * math.sin(4 * ang)
    if sx == 0.0 and sy == 0.0:
        return 0.0
    return math.atan2(sy, sx) / 4.0


def _regularize_orthogonal(axes, max_thick, min_len):
    """Snäppää seinät ortogonaalirunkoon ja sulauta saman seinän rinnakkaispinnat."""
    if not axes:
        return axes
    theta = _dominant_angle(axes)
    c, s = math.cos(-theta), math.sin(-theta)

    def rot(p, cc, ss):
        return [cc * p[0] - ss * p[1], ss * p[0] + cc * p[1]]

    # paikalliseen runkoon
    local = []
    for a_s, a_e, t in axes:
        ls = rot(a_s, c, s); le = rot(a_e, c, s)
        dx = le[0] - ls[0]; dy = le[1] - ls[1]
        horizontal = abs(dx) >= abs(dy)
        if horizontal:
            y = 0.5 * (ls[1] + le[1])
            ls = [ls[0], y]; le = [le[0], y]
        else:
            x = 0.5 * (ls[0] + le[0])
            ls = [x, ls[1]]; le = [x, le[1]]
        local.append([ls, le, t, horizontal])

    # sulauta rinnakkais-päällekkäiset (sama seinä, kaksi pintaa / katkokset)
    merged = _merge_axis_lines(local, max_thick)

    # sulje nurkat paikallisrungossa: jatka päätepisteet kohtisuoraan naapuriin
    merged = _close_corners_local(merged, max_thick)

    # takaisin maailmankoordinaatistoon
    cc, ss = math.cos(theta), math.sin(theta)
    out = []
    for ls, le, t, _h in merged:
        ws = rot(ls, cc, ss); we = rot(le, cc, ss)
        if _dist(ws, we) >= min_len:
            out.append((ws, we, t))
    return out


_CORNER_REACH = 900.0  # mm — kuinka kauas päätepiste saa hakea kohtisuoran naapurin


def _close_corners_local(lines, max_thick):
    """Paikallisrungossa (H/V): jatka/snäppää päätepisteet kohtisuoraan naapuriseinään.

    Kaksi kierrosta konvergenssia varten (V-seinät siirtyvät ensimmäisellä,
    H-seinät kohdistuvat toisella).
    """
    h_lines = [ln for ln in lines if ln[3]]   # vaakaseinät: y vakio, vaihtelee x
    v_lines = [ln for ln in lines if not ln[3]]

    for _ in range(2):
        # H-pää → lähin V-seinä (x-arvo); huomioi V:n pituuskattavuus (jatketulla varalla)
        for h in h_lines:
            ys = h[0][1]
            for end in (0, 1):
                x = h[end][0]
                best = None; bestd = _CORNER_REACH
                for v in v_lines:
                    vx = v[0][0]
                    vy0, vy1 = sorted([v[0][1], v[1][1]])
                    if vy0 - _CORNER_REACH <= ys <= vy1 + _CORNER_REACH:
                        d = abs(vx - x)
                        if d < bestd:
                            bestd = d; best = vx
                if best is not None:
                    h[end][0] = best
        for v in v_lines:
            xs = v[0][0]
            for end in (0, 1):
                y = v[end][1]
                best = None; bestd = _CORNER_REACH
                for h in h_lines:
                    hy = h[0][1]
                    hx0, hx1 = sorted([h[0][0], h[1][0]])
                    if hx0 - _CORNER_REACH <= xs <= hx1 + _CORNER_REACH:
                        d = abs(hy - y)
                        if d < bestd:
                            bestd = d; best = hy
                if best is not None:
                    v[end][1] = best
    return lines


def _merge_axis_lines(local, max_thick):
    """Yhdistä samansuuntaiset (H/H tai V/V) lähekkäiset päällekkäiset akselit yhdeksi."""
    used = [False] * len(local)
    result = []
    for i in range(len(local)):
        if used[i]:
            continue
        lsi, lei, ti, hi = local[i]
        # kerää klusteri samansuuntaisia lähellä olevia
        if hi:
            pos = 0.5 * (lsi[1] + lei[1]); lo = min(lsi[0], lei[0]); hi_ = max(lsi[0], lei[0])
        else:
            pos = 0.5 * (lsi[0] + lei[0]); lo = min(lsi[1], lei[1]); hi_ = max(lsi[1], lei[1])
        positions = [pos]; thicks = [ti]
        used[i] = True
        for j in range(i + 1, len(local)):
            if used[j]:
                continue
            lsj, lej, tj, hj = local[j]
            if hj != hi:
                continue
            if hj:
                pj = 0.5 * (lsj[1] + lej[1]); jlo = min(lsj[0], lej[0]); jhi = max(lsj[0], lej[0])
            else:
                pj = 0.5 * (lsj[0] + lej[0]); jlo = min(lsj[1], lej[1]); jhi = max(lsj[1], lej[1])
            # sama akseli jos kohtisuora etäisyys < max_thick ja peittää pituussuunnassa
            overlap = min(hi_, jhi) - max(lo, jlo)
            if abs(pj - pos) <= max_thick and overlap > -max_thick:
                positions.append(pj); thicks.append(tj)
                lo = min(lo, jlo); hi_ = max(hi_, jhi)
                used[j] = True
        new_pos = float(np.mean(positions))
        # paksuus: jos kaksi erillistä pintaa → niiden etäisyys, muuten siemen
        spread = max(positions) - min(positions)
        thick = spread if (len(positions) >= 2 and 50.0 <= spread <= max_thick) else float(np.mean(thicks))
        if hi:
            result.append([[lo, new_pos], [hi_, new_pos], thick, True])
        else:
            result.append([[new_pos, lo], [new_pos, hi_], thick, False])
    return result


# ---------------------------------------------------------------------------
# Detektori
# ---------------------------------------------------------------------------

@DetectorRegistry.register("contour")
class WallDetectorContour(ElementDetector):
    """Ääriviivapohjainen seinädetektori (Cloud2BIM-tyyli)."""

    def __init__(
        self,
        pixel_size: float = _PIXEL_SIZE,
        density_threshold: int = _DENSITY_THRESHOLD,
        close_kernel: int = _CLOSE_KERNEL,
        dp_tol: float = _DP_TOL,
        min_wall_length: float = _MIN_WALL_LENGTH,
        min_thickness: float = _MIN_THICKNESS,
        max_thickness: float = _MAX_THICKNESS,
    ) -> None:
        self.pixel_size = pixel_size
        self.density_threshold = density_threshold
        self.close_kernel = close_kernel
        self.dp_tol = dp_tol
        self.min_wall_length = min_wall_length
        self.min_thickness = min_thickness
        self.max_thickness = max_thickness
        self.semantic_labels = None   # SemanticLabels|None, pipeline asettaa

    def detect(self, cloud: o3d.geometry.PointCloud) -> StructuralModel:
        # Raskas rasterointi → aja harvennetulle pilvelle (muisti/nopeus).
        if len(cloud.points) > _MAX_WORK_POINTS:
            voxel = 15.0
            work = cloud.voxel_down_sample(voxel)
            while len(work.points) > _MAX_WORK_POINTS and voxel < 80.0:
                voxel *= 1.4
                work = cloud.voxel_down_sample(voxel)
            pts = np.asarray(work.points)
        else:
            pts = np.asarray(cloud.points)
        if len(pts) < 500:
            return StructuralModel()

        walls = self._extract(pts)
        model = StructuralModel(walls=walls)
        model.metadata = Metadata(detector_method="contour")
        return model

    # --- vaiheet -----------------------------------------------------------

    def _extract(self, pts: np.ndarray) -> list[Wall]:
        z = pts[:, 2]
        z_min_all, z_max_all = float(z.min()), float(z.max())
        # Lattia + katto z-tiheyspiikeistä → kaista lasketaan niiden välistä,
        # ei koko z-alueesta (muuten kaista osuu kattolaattaan = täysi maski).
        floor_z, ceil_z = _floor_ceiling(z, z_min_all, z_max_all)
        span = ceil_z - floor_z
        z_lo = floor_z + _Z_BAND[0] * span
        z_hi = floor_z + _Z_BAND[1] * span
        band = pts[(z >= z_lo) & (z <= z_hi)]
        if len(band) < 200:
            band = pts
        xy = band[:, :2]

        # Monikerros-pystymaski koko vapaalta korkeudelta (lattia+pohja → katto−ylä):
        # suodattaa osakorkuiset kalusteet pois. Fallback yhden kaistan tiheyteen
        # jos korkeus on liian matala viipalointiin.
        clear = pts[(z >= floor_z + _VSLICE_BOTTOM) & (z <= ceil_z - _VSLICE_TOP)]
        if len(clear) >= 200 and (ceil_z - _VSLICE_TOP) - (floor_z + _VSLICE_BOTTOM) >= 4 * _VSLICE_STEP:
            binary, x_min, y_min = self._vertical_mask(clear, floor_z, ceil_z)
        else:
            binary, x_min, y_min = self._binary_mask(xy)
        # RETR_CCOMP: ulkoreuna + reiät (huoneiden ääriviivat). Reikien reunat ovat
        # sisäseinien pinnat → niistä saadaan väliseinät, ei vain perimetri.
        contours, _ = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return []

        # pikseli → maailma (mm)
        segments = self._contours_to_segments(contours, x_min, y_min)

        # lyhyet pois
        segments = [s for s in segments if _dist(s[0], s[1]) >= self.min_wall_length]
        if not segments:
            return []

        # yhdistä samalla suoralla
        segments = _merge_collinear(segments, self.min_thickness, self.max_thickness)

        # Parita vastakkaiset pinnat → paksut seinät joiden akseli = keskiviiva.
        # Ohuet seinät näkyvät maskissa yhtenä viivana (kontuuri kiertää tiukasti)
        # → ne jäävät parittomiksi ja tulkitaan suoraan keskiviivaksi. Pipeline
        # mittaa todellisen paksuuden + tarkentaa akselin pistepilvestä.
        groups, unpaired = _group_segments(segments, self.max_thickness)

        # akseli + paksuus per ryhmä (korkeus = lattia–katto; pipeline normalisoi)
        z_min_w = floor_z
        height = max(span, 2000.0)
        axes: list[tuple[list, list, float]] = []  # (p0, p1, thickness_seed)

        for group in groups:
            res = _wall_axis(group)
            if res is None:
                continue
            (a_s, a_e), thick = res
            thick = min(max(thick, self.min_thickness), self.max_thickness)
            if _dist(a_s, a_e) >= self.min_wall_length:
                axes.append((a_s, a_e, thick))

        # parittomat segmentit = ohuiden seinien keskiviivat suoraan
        for seg in unpaired:
            if _dist(seg[0], seg[1]) >= self.min_wall_length:
                axes.append((list(seg[0]), list(seg[1]), _DEFAULT_THICKNESS))

        # Ortogonaalinen regularisointi + rinnakkaisduplikaattien sulautus:
        # huoneisto on ~vinossa maailmankoordinaatistossa → snäppää seinät yhteiseen
        # ortogonaaliseen runkoon ja yhdistä saman seinän kaksi pintaa yhdeksi akseliksi.
        axes = _regularize_orthogonal(axes, self.max_thickness, self.min_wall_length)

        walls: list[Wall] = []
        for a_s, a_e, thick in axes:
            length = _dist(a_s, a_e)
            # Korkea tasainen pohja: kaikki kontuuriseinät ovat yhtä päteviä (seinämassasta).
            # Estää pipelinen confidence-kynnystä (max*0.30) karsimasta lyhyitä-mutta-oikeita.
            conf = round(min(1.0, 0.80 + length / 20000.0), 3)
            walls.append(Wall(
                id=f"wall_{len(walls):03d}",
                confidence=conf,
                classification="wall",
                source=ElementSource(method="contour"),
                axis=[[round(float(a_s[0]), 1), round(float(a_s[1]), 1)],
                      [round(float(a_e[0]), 1), round(float(a_e[1]), 1)]],
                height=round(float(height), 1),
                thickness=round(float(thick), 1),
                z_min=round(float(z_min_w), 1),
            ))
        return walls

    def _vertical_mask(self, clear: np.ndarray, floor_z: float, ceil_z: float):
        """Monikerros-pystymaski: pikseli on seinää vain jos se täyttyy isossa
        osassa vaakaviipaleita (= ulottuu lattiasta kattoon). Kalusteet, jotka
        täyttävät vain osan korkeudesta, putoavat pois."""
        xy = clear[:, :2]
        z = clear[:, 2]
        x_min, y_min = float(xy[:, 0].min()), float(xy[:, 1].min())
        cols = max(int((xy[:, 0].max() - x_min) / self.pixel_size) + 1, 1)
        rows = max(int((xy[:, 1].max() - y_min) / self.pixel_size) + 1, 1)
        xr = [x_min, x_min + cols * self.pixel_size]
        yr = [y_min, y_min + rows * self.pixel_size]

        z0 = floor_z + _VSLICE_BOTTOM
        z1 = ceil_z - _VSLICE_TOP
        edges = np.arange(z0, z1 + _VSLICE_STEP, _VSLICE_STEP)
        n_sl = len(edges) - 1
        # Korkeassa tilassa osuussääntö ei päde (ks. _VSLICE_TALL_MM) → seurataan
        # myös pisintä YHTÄJAKSOISTA pystyjaksoa. Matalassa tilassa tätä ei lasketa
        # lainkaan, joten asuintilojen tulos pysyy bitilleen ennallaan.
        tall = (ceil_z - floor_z) > _VSLICE_TALL_MM
        run_need = max(2, int(round(_VSLICE_RUN_MM / _VSLICE_STEP)))
        cur = np.zeros((rows, cols), dtype=np.int32) if tall else None
        best = np.zeros((rows, cols), dtype=np.int32) if tall else None

        vcount = np.zeros((rows, cols), dtype=np.int32)
        for k in range(n_sl):
            m = (z >= edges[k]) & (z < edges[k + 1])
            if int(m.sum()) < 10:
                if tall:
                    cur[:] = 0
                continue
            grid, _, _ = np.histogram2d(
                xy[m, 0], xy[m, 1], bins=[cols, rows], range=[xr, yr])
            occ = grid.T >= _VSLICE_MIN_PER
            vcount += occ.astype(np.int32)
            if tall:
                cur = np.where(occ, cur + 1, 0)
                np.maximum(best, cur, out=best)

        need = max(2, int(round(_VSLICE_FRAC * n_sl)))
        passed = vcount >= need
        if tall:
            passed |= best >= run_need
            sem = self._semantic_run(clear, edges, rows, cols, xr, yr)
            if sem is not None:
                passed |= sem
        binary = passed.astype(np.uint8) * 255
        kernel = np.ones((self.close_kernel, self.close_kernel), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return binary, x_min, y_min

    def _semantic_run(self, clear, edges, rows, cols, xr, yr):
        """Pystyjakso laskettuna VAIN seinäluokan pisteistä, löysemmällä
        kynnyksellä. None jos labeleita ei ole."""
        labels = self.semantic_labels
        if labels is None:
            return None
        try:
            from scan2bim.core.segmentation.pointnet_filter import S3DIS_WALL
            lab = labels.lookup(clear)
        except Exception:
            return None
        wall = clear[lab == S3DIS_WALL]
        if len(wall) < 200:
            return None
        need = max(2, int(round(_VSLICE_RUN_SEM_MM / _VSLICE_STEP)))
        xy, z = wall[:, :2], wall[:, 2]
        cur = np.zeros((rows, cols), dtype=np.int32)
        best = np.zeros((rows, cols), dtype=np.int32)
        for k in range(len(edges) - 1):
            m = (z >= edges[k]) & (z < edges[k + 1])
            if int(m.sum()) < 10:
                cur[:] = 0
                continue
            grid, _, _ = np.histogram2d(
                xy[m, 0], xy[m, 1], bins=[cols, rows], range=[xr, yr])
            occ = grid.T >= _VSLICE_MIN_PER
            cur = np.where(occ, cur + 1, 0)
            np.maximum(best, cur, out=best)
        return best >= need

    def _binary_mask(self, xy: np.ndarray):
        x_min, y_min = float(xy[:, 0].min()), float(xy[:, 1].min())
        cols = max(int((xy[:, 0].max() - x_min) / self.pixel_size) + 1, 1)
        rows = max(int((xy[:, 1].max() - y_min) / self.pixel_size) + 1, 1)
        grid, _, _ = np.histogram2d(
            xy[:, 0], xy[:, 1], bins=[cols, rows],
            range=[[x_min, x_min + cols * self.pixel_size],
                   [y_min, y_min + rows * self.pixel_size]],
        )
        binary = (grid.T >= self.density_threshold).astype(np.uint8) * 255
        # skimage.morphology.closing(footprint_rectangle((k,k))) -vastine OpenCV:llä
        kernel = np.ones((self.close_kernel, self.close_kernel), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return binary, x_min, y_min

    def _contours_to_segments(self, contours, x_min, y_min):
        eps = self.dp_tol  # mm; approxPolyDP epsilon pikseleinä → jaa pixel_sizella
        segments = []
        for cnt in contours:
            approx = cv2.approxPolyDP(cnt, eps / self.pixel_size, True)
            pts = [(float(p[0][0]), float(p[0][1])) for p in approx]
            for i in range(len(pts)):
                a = pts[i - 1]; b = pts[i]
                seg = [
                    [a[0] * self.pixel_size + x_min, a[1] * self.pixel_size + y_min],
                    [b[0] * self.pixel_size + x_min, b[1] * self.pixel_size + y_min],
                ]
                segments.append(seg)
        return segments


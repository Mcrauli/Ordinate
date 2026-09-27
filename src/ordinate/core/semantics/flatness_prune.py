"""Poista seinä jonka kaistassa ei ole TASOA.

Kaikki aiemmat portit kysyvät onko seinän kohdalla pintaa — putkikellarissa on
aina. Tämä kysyy onko se pinta TASO. Aito seinäpinta on taso: kaistan pisteiden
kohtisuora hajonta on muutamia millimetrejä. Putki, kanava ja kaapeli täyttävät
kaistan tasaisesti, jolloin hajonta on kymmeniä millimetrejä. Hajonta on mitta
pinnasta itsestään — se ei riipu keilaustiheydestä, huonekorkeudesta eikä
siitä näkyykö seinästä kolmannes vai kaikki, ja juuri siihen kaatuivat
seinämäinen kate, komponenttikoko ja jatkuvuus.

Mitattu kaistan mediaanihajonta (500 mm sarakkeina, 120 mm kaista):

  | aineisto           | MAD    | tasomaisia sarakkeita |
  |--------------------|--------|-----------------------|
  | liiketila          |  2.1 mm| 1.00                  |
  | asunto             |  4.2 mm| 0.94                  |
  | Rohbau (5 sceneä)  |  2.8–6.1 mm | 0.88–0.94        |
  | synteettinen       | 14.6 mm| 0.57                  |
  | **koulun kellari** |**28.7 mm**| **0.25**           |

Kellarin seinäkaistassa ei siis ole tasoa. Kynnys 0.20 on mitattu turvalliseksi
kaikilla yhdeksällä vertailuaineistolla: Rohbaun viidestä scenestä poistuu
kolme lyhyttä `wall_ext`-seinää eikä GT-kattavuus muutu yhdessäkään
(scene_07003:n GT-TARKKUUS nousee 0.912 → 0.923), asunto, liiketila ja
synteettinen eivät menetä yhtään seinää. Kellarista poistuu 27.

**ANSA — älä tee kynnyksestä suhteellista.** Kokeiltu: sarake on taso jos sen
hajonta on alle 3 × mallin oman p10-hajonnan. Se on paljon huonompi, koska
p10 on 1–2.5 mm joka aineistossa (yksi hyvin keilattu sarake löytyy aina) →
raja 6 mm hylkää asunnon mediaanin 0.94 → 0.59 ja synteettisen 0.57 → 0.14.
20 mm on fysikaalinen: sitä paksumpi hajonta ei ole rakennettu taso.
"""
from __future__ import annotations

import numpy as np

_COL = 500.0        # mm — sarake pituussuunnassa
_BAND = 120.0       # mm — kaista pinnan ympärillä
_MIN_PTS = 30       # sarakkeessa oltava näin monta pistettä
_FLAT_MM = 20.0     # mm — MAD tätä pienempi = taso
_MIN_FRAC = 0.20    # osuus sarakkeista jotka on oltava tasoa
_MIN_LEN = 2000.0   # mm — lyhyt seinä ei kerää tarpeeksi sarakkeita
_VOXEL = 10.0       # mm — hajonta ei tarvitse täyttä resoluutiota
_WAIST_LO, _WAIST_HI = 0.25, 0.75


def flat_fraction(wall, pts: np.ndarray, index) -> float | None:
    """Osuus seinän sarakkeista joissa kaista on taso, tai None jos ei näyttöä."""
    from ordinate.core.geometry.xy_index import subset  # noqa: PLC0415

    axis = getattr(wall, "axis", None)
    if not axis or len(axis) < 2:
        return None
    p0 = np.asarray(axis[0], dtype=float)[:2]
    p1 = np.asarray(axis[-1], dtype=float)[:2]
    length = float(np.linalg.norm(p1 - p0))
    if length < _MIN_LEN:
        return None
    u = (p1 - p0) / length
    n = np.array([-u[1], u[0]])
    half = float(getattr(wall, "thickness", 200.0)) / 2.0

    near, _ = subset(pts, index, p0, u, n, half + _BAND, 0.0, length)
    if len(near) < _MIN_PTS:
        return None
    d = near[:, :2] - p0
    s, t = d @ u, d @ n
    n_col = max(int(length / _COL), 1)
    col = np.clip((s / _COL).astype(int), 0, n_col - 1)

    seen = flat = 0
    for c in range(n_col):
        sel = col == c
        if int(sel.sum()) < _MIN_PTS:
            continue
        tc = t[sel]
        # Kaista ei saa ylettya seinan KESKILINJAN yli: 66 mm seinalla
        # +-120 mm nielaisee vastapinnan ja hajonta on aina iso riippumatta
        # siita onko pinta taso. Mitattu: synteettisen `wall_001` (66 mm)
        # sai 0.14 ja putosi, vaikka se on aito seina.
        b = min(_BAND, max(half, 20.0))
        for side in (-half, half):
            band = tc[np.abs(tc - side) < b]
            if len(band) < _MIN_PTS:
                continue
            mad = float(np.median(np.abs(band - np.median(band))))
            seen += 1
            flat += mad < _FLAT_MM
            break
    return flat / seen if seen else None


def prune_flatless_walls(model, cloud, floor_z: float,
                         ceiling_z: float) -> list[str]:
    """Poista seinät joiden kaistassa ei ole tasoa. Palauttaa poistettujen id:t."""
    import open3d as o3d  # noqa: PLC0415

    from ordinate.core.geometry.xy_index import XYIndex  # noqa: PLC0415

    if not model.walls or ceiling_z - floor_z < 700.0:
        return []
    pts = np.asarray(cloud.points)
    if len(pts) < 1000:
        return []
    lo = floor_z + _WAIST_LO * (ceiling_z - floor_z)
    hi = floor_z + _WAIST_HI * (ceiling_z - floor_z)
    band = pts[(pts[:, 2] > lo) & (pts[:, 2] < hi)]
    if len(band) < 1000:
        return []
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(band)
    band = np.asarray(pc.voxel_down_sample(_VOXEL).points)
    del pc
    if len(band) < 1000:
        return []

    index = XYIndex(band)
    drop = []
    for w in model.walls:
        frac = flat_fraction(w, band, index)
        if frac is not None and frac < _MIN_FRAC:
            drop.append(w.id)
    if drop:
        keep = set(drop)
        model.walls = [w for w in model.walls if w.id not in keep]
    return drop

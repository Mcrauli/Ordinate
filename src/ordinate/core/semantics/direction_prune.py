"""Poista seinä joka on piirretty suuntaan jossa pilvessä ei ole pintaa.

Mitattu koulun kellarilla: **58 % mallin seinäpituudesta (238 m / 411 m) kulkee
suuntaan jota detektori ei löytänyt lainkaan**, ja kaksi parhaiten tuettua
suuntaa (21° ja 111°, 17 % ja 15 % normaalimassasta) oli mallinnettu 2.9 m ja
0.0 m. Ne 238 m ovat niitä pitkiä vinoja linjoja jotka läpäisevät kaikki muut
portit: ne ovat tasomaisia jossain ja koskettavat pintaa siellä täällä.

Suunnat eivät ole detektorin keksimiä vaan ketjun: `regularize_orthogonal`,
nurkkasnäppäys, perimetri ja kollineaarinen sulautus siirtävät akseleita, ja
lopputulos ei enää osoita mihinkään mitattuun pintaan.

Mittari on pilven OMA jakauma: seinämäisten pystypintapisteiden normaalien
kulmahistogrammi, ja seinän suunta siitä luettuna suhteessa histogrammin
maksimiin. Mitattu:

  | aineisto      | min  | mediaani | alle 0.30 |
  |---------------|------|----------|-----------|
  | liiketila     | 0.86 | 0.86     | 0 m       |
  | asunto        | 0.54 | 1.00     | 0 m       |
  | Rohbau 07000  | 0.00 | 0.78     | 3 m / 226 |
  | Rohbau 07003  | 0.02 | 0.49     | 2 m / 98  |
  | **kellari**   | 0.03 | **0.14** | **208 m / 358** |

**TÄMÄ EI OLE `drop_skew` UUDELLEEN.** Se pudotti seinän joka poikkesi yli 22°
PERHESUUNNASTA eli geometrisesta Manhattan-priorista, ja kaatui siihen että
kellarissa on kuusi aitoa suuntaa 20° välein. Tämä ei oleta suuntien määrää
eikä niiden välejä: jos rakennuksessa on kuusi suuntaa, kaikki kuusi näkyvät
histogrammissa ja kaikki kuusi kelpaavat.

Kynnys 0.20 on mitattu ylärajaksi: 0.30 romahduttaa Rohbau scene_07002:n
GT-kattavuuden 0.863 → 0.524, kun 0.20 jättää sen koskematta. 0.20:llä
Rohbausta poistuu kaksi seinää viidestä scenestä eikä yksikään menetä
GT-kattavuutta (07003:n GT-tarkkuus nousee 0.921 → 0.923); asunto ja liiketila
eivät menetä yhtään seinää.
"""
from __future__ import annotations

import numpy as np

_BIN = 2.0          # astetta — kulmahistogrammin bini
_TOL = 6.0          # astetta — kuinka läheltä huippua seinän suunta luetaan
_MIN_FRAC = 0.20    # osuus histogrammin maksimista
_MIN_LEN = 2000.0   # mm — lyhyt seinä ei kanna suuntatietoa


def _histogram(wallish_xyz: np.ndarray):
    import open3d as o3d  # noqa: PLC0415

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(np.asarray(wallish_xyz, dtype=np.float64))
    pc.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=24))
    n = np.asarray(pc.normals)
    ang = np.degrees(np.arctan2(n[:, 1], n[:, 0])) % 180.0
    hist, edges = np.histogram(ang, bins=int(180.0 / _BIN), range=(0.0, 180.0))
    return hist, 0.5 * (edges[:-1] + edges[1:])


def direction_support(wall, hist, centers, peak: float) -> float | None:
    """Seinän suunnan normaalimassa suhteessa maksimiin, tai None jos lyhyt."""
    axis = getattr(wall, "axis", None)
    if not axis or len(axis) < 2:
        return None
    a = np.asarray(axis[0], dtype=float)[:2]
    b = np.asarray(axis[-1], dtype=float)[:2]
    if float(np.linalg.norm(b - a)) < _MIN_LEN:
        return None
    deg = (np.degrees(np.arctan2(b[1] - a[1], b[0] - a[0])) + 90.0) % 180.0
    near = np.abs((centers - deg + 90.0) % 180.0 - 90.0) < _TOL
    if not near.any():
        return None
    return float(hist[near].max()) / peak


def prune_offdirection_walls(model, cloud, floor_z: float, ceiling_z: float,
                             wallish=None) -> list[str]:
    """Poista seinät joiden suunnassa ei ole pintaa. Palauttaa poistettujen id:t."""
    from ordinate.core.semantics.contrast_prune import wallish_of  # noqa: PLC0415

    if not model.walls:
        return []
    got = wallish_of(cloud, floor_z, ceiling_z) if wallish is None else wallish
    if got is None:
        return []
    mask, q = got
    W = q[mask]
    if len(W) < 1000:
        return []
    hist, centers = _histogram(W)
    peak = float(hist.max())
    if peak <= 0.0:
        return []

    drop = []
    for w in model.walls:
        s = direction_support(w, hist, centers, peak)
        if s is not None and s < _MIN_FRAC:
            drop.append(w.id)
    if drop:
        keep = set(drop)
        model.walls = [w for w in model.walls if w.id not in keep]
    return drop

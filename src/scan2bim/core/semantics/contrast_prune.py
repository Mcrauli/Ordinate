"""Poista seinä jonka kohdalla ei ole enempää pintaa kuin sen vierellä.

`prune_unsupported_walls` kysyy onko seinän kaistassa PISTEITÄ. Matalassa
talotekniikkakellarissa vastaus on aina kyllä: mitattu koulun kellarilla 396
seinästä, sarakekate p10 **1.00** ja mediaani **1.00** — jokaisen linjan
varrella on putki, kanava tai kaapeli, joten sääntö mittaa rakennusta eikä
seinää.

Erottava kysymys ei ole PALJONKO pintaa on vaan onko sitä siinä ENEMMÄN KUIN
VIERESSÄ. Aito seinä erottuu ympäristöstään; putkimetsän läpi vedetty viiva ei,
koska putkia on yhtä paljon joka puolella. Suhde on dimensioton eikä riipu
keilaustiheydestä, huonekorkeudesta eikä pistevälistä — sama luku tarkoittaa
samaa asiaa 1.8 m kellarissa ja 10 m hallissa. Mitattu kontrasti mallin seinistä:

  | aineisto     | min  | mediaani |
  |--------------|------|----------|
  | asunto       | 1.87 | 2.40     |
  | liiketila    | 1.95 | 43.5     |
  | Rohbau (5)   | 1.00 | 1.9–2.1  |
  | **kellari**  | 0.01 | **1.00** |

Kellarin tyypillisen mallinnetun seinän kohdalla on siis täsmälleen yhtä paljon
pystypintaa kuin metrin sivussa.

**SOKEUSEHTO — tämä on se mikä tekee säännöstä turvallisen.** Rohbaun 10 m
hallissa seinämäisyys vaatii pystypintaa yli puolet kaistan korkeudesta, ja
lattialta keilatusta seinästä näkyy kolmannes: kokonaisia aitoja seiniä jää
ilman yhtään seinämäistä pistettä KUMMALLAKAAN puolella. Silloin kontrasti on
1.00 pelkästä nollasta eikä se ole todiste mistään. Sääntö tuomitsee vain
siellä missä mittarilla on voimaa: seinän ±3 m ympäristössä on oltava pintaa
vähintään `_POWER_FRAC` verran mallin OMASTA mediaanista. Mitattu ero on selvä
— Rohbaun tyhjien seinien ympäristö on 0 pistettä/m, kellarin 31–64 kun mallin
mediaani on 143.

Mitattu vaikutus (sama malli, sääntö jälkikäteen ajettuna):
  | aineisto     | poistuu | GT-kattavuus | GT-tarkkuus     |
  |--------------|---------|--------------|-----------------|
  | rohbau_07000 | 0/8     | 0.886 → 0.886| 0.914 → 0.914   |
  | rohbau_07001 | 1/5     | 0.863 → 0.863| 0.864 → **0.957** |
  | rohbau_07002 | 0/6     | 0.859 → 0.859| 0.964 → 0.964   |
  | rohbau_07003 | 1/8     | 0.824 → 0.824| 0.912 → 0.912   |
  | rohbau_07004 | 0/5     | 0.755 → 0.755| 0.927 → 0.927   |
  | kellari      | 55/125  | 0.233 → 0.232| 0.163 → **0.221** |
"""
from __future__ import annotations

import numpy as np

_CTRL = (750.0, 1250.0)   # mm — kontrollietäisyydet seinäpinnan sivussa
_BAND = 80.0              # mm — kaista pinnan ympärillä (sama kuin qa/coverage)
_NEAR = 3000.0            # mm — ympäristö jolla mittarin voima mitataan
_POWER_FRAC = 0.10        # osuus mallin mediaanitiheydestä: alle tämän ei tuomita
_MIN_LEN = 2000.0         # mm — lyhyt seinä ei kerää tarpeeksi näyttöä
_MARGIN = 1.0             # kontrasti tämän alle = pintaa on vähemmän kuin vieressä


def _measure(wall, W: np.ndarray):
    """(kontrasti, ympäristötiheys pistettä/m) tai None jos seinä on lyhyt."""
    axis = getattr(wall, "axis", None)
    if not axis or len(axis) < 2:
        return None
    a = np.asarray(axis[0], dtype=float)[:2]
    b = np.asarray(axis[-1], dtype=float)[:2]
    length = float(np.linalg.norm(b - a))
    if length < _MIN_LEN:
        return None
    u = (b - a) / length
    n = np.array([-u[1], u[0]])
    half = float(getattr(wall, "thickness", 200.0)) / 2.0

    d = W - a
    s, t = d @ u, d @ n
    span = (s > -1000.0) & (s < length + 1000.0)
    at = np.abs(t)
    on = int((span & (np.abs(at - half) < _BAND)).sum())
    # Kontrolli mitataan PINNASTA ULOSPÄIN. `at` on itseisarvo, joten yksi
    # etäisyys kattaa jo seinän molemmat puolet; `half - c` osuisi seinän
    # sisään, jossa ei ole koskaan pintaa, ja painaisi mediaanin nollaan.
    ctrl = [int((span & (np.abs(at - (half + c)) < _BAND)).sum()) for c in _CTRL]
    near = int((span & (at < _NEAR)).sum())
    return (on + 1.0) / (float(np.median(ctrl)) + 1.0), near / (length / 1000.0)


def prune_uncontrasted_walls(model, cloud, floor_z: float,
                             ceiling_z: float) -> list[str]:
    """Poista seinät jotka eivät erotu ympäristöstään. Palauttaa poistettujen id:t."""
    from scan2bim.core.qa.coverage import wallish_points  # noqa: PLC0415

    if not model.walls:
        return []
    pts = np.asarray(cloud.points)
    if len(pts) < 1000 or ceiling_z - floor_z < 700.0:
        return []
    mask, q = wallish_points(pts, floor_z + 400.0, ceiling_z - 300.0)
    if not mask.any():
        return []
    W = q[mask][:, :2]

    measured = {}
    for w in model.walls:
        m = _measure(w, W)
        if m is not None:
            measured[w.id] = m
    if len(measured) < 3:
        return []

    ref = float(np.median([m[1] for m in measured.values()]))
    if ref <= 0.0:
        return []
    drop = {wid for wid, (contrast, dens) in measured.items()
            if dens >= _POWER_FRAC * ref and contrast <= _MARGIN}
    if drop:
        model.walls = [w for w in model.walls if w.id not in drop]
    return sorted(drop)

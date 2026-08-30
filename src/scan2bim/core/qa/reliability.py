"""Kertooko malli itse olevansa epäluotettava?

Koulun kellari tuotti 427 seinää joista valtaosa oli valeseiniä, eikä yksikään
putken oma luku varoittanut siitä: `confidence` on kokoproxy, `support` ja
`continuity` mittaavat TASOA joka riippuu skannista, ja QA:n tarkistuslista jäi
lyhyeksi. Vika löytyi vasta kun malli piirrettiin kuvaksi ja katsottiin.

Tämä laskee ne kolme signaalia jotka siinä aineistossa erottelivat, ja jotka
ovat suhdelukuja eivätkä tasoja — sama luku tarkoittaa samaa asiaa 1.8 m
kellarissa ja 10 m hallissa:

  KONTRASTI   pystypintaa seinän pinnalla vs. 0.75–1.25 m sen vierellä.
              Mitattu: asunto 2.40, liiketila 43.5, Rohbau 1.9–2.1,
              kellari 1.00 — kellarin seinä ei eroa ympäristöstään.
  PAKSUUS     mallin paksuus vs. pinnoista mitattu piikkipari.
              Mitattu: asunto 154 vs 150 mm, Rohbau 120 vs 112 mm,
              kellari 66 vs 225 mm.
  SIJAINTI    onko seinän oma pinta siellä minne malli sen piirtää.
              Mitattu osuvia: asunto ja liiketila 100 %, kellari 27 %.

Raportti ei korjaa mitään — se kertoo mitä ei kannata uskoa. Uusi skanni ei saa
jäädä kiinni siitä katsooko joku kuvia.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

_ON = 80.0                # mm — kaista pinnan ympärillä
_CTRL = (750.0, 1250.0)   # mm — kontrollietäisyydet pinnasta ulospäin
_MIN_LEN = 2000.0         # mm — lyhyt seinä ei kerää näyttöä
_CONTRAST_BAD = 1.20      # tämän alle jäävä mediaani = seinät eivät erotu
_HIT_BAD = 0.50           # tätä pienempi osuva-osuus = malli on väärässä paikassa
_THICK_BAD = 60.0         # mm — mediaanipoikkeama pinnoista mitattuun


@dataclass
class Reliability:
    walls: int = 0
    judged: int = 0
    contrast_median: float | None = None
    hit_frac: float | None = None
    thickness_bias: float | None = None
    warnings: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"Luotettavuus: {self.judged}/{self.walls} seinää mitattu"]
        if self.contrast_median is not None:
            out.append(f"  kontrasti ympäristöön (mediaani): {self.contrast_median:.2f}")
        if self.hit_frac is not None:
            out.append(f"  seiniä oman pintansa päällä: {self.hit_frac:.0%}")
        if self.thickness_bias is not None:
            out.append(f"  paksuusero pinnoista mitattuun: {self.thickness_bias:+.0f} mm")
        out.extend(f"  VAROITUS: {w}" for w in self.warnings)
        return out


def _peak_pair(t: np.ndarray) -> float | None:
    """Pintojen etäisyys: vahvin piikki ja vahvin piikki TOISELTA puolelta."""
    if len(t) < 200:
        return None
    edges = np.arange(-400.0, 401.0, 25.0)
    hist, _ = np.histogram(t, bins=edges)
    if hist.max() < 20:
        return None
    centers = 0.5 * (edges[:-1] + edges[1:])
    i = int(np.argmax(hist))
    opp = np.flatnonzero(np.sign(centers) != np.sign(centers[i]))
    if not len(opp):
        return None
    j = int(opp[np.argmax(hist[opp])])
    if hist[j] < 0.15 * hist[i]:
        return None
    return float(abs(centers[i] - centers[j]))


def measure(model, cloud, floor_z: float, ceiling_z: float,
            wallish=None) -> Reliability:
    """Mallin luotettavuussignaalit pilveä vasten. Ei muuta mallia.

    `wallish` on `semantics/contrast_prune.wallish_of`:n paluuarvo — sama
    joukko kelpaa molemmille eikä normaaleja tarvitse estimoida kahdesti.
    """
    from scan2bim.core.semantics.contrast_prune import wallish_of  # noqa: PLC0415

    rep = Reliability(walls=len(model.walls))
    if not model.walls or len(np.asarray(cloud.points)) < 1000:
        return rep
    got = wallish_of(cloud, floor_z, ceiling_z) if wallish is None else wallish
    if got is None:
        rep.warnings.append("pilvestä ei löydy yhtään seinämäistä pystypintaa")
        return rep
    mask, q = got
    W = q[mask][:, :2]
    zs = q[:, 2]
    band = q[(zs > np.percentile(zs, 20)) & (zs < np.percentile(zs, 80))]

    contrasts: list[float] = []
    hits: list[bool] = []
    biases: list[float] = []
    for w in model.walls:
        axis = getattr(w, "axis", None)
        if not axis or len(axis) < 2:
            continue
        a = np.asarray(axis[0], dtype=float)[:2]
        b = np.asarray(axis[-1], dtype=float)[:2]
        length = float(np.linalg.norm(b - a))
        if length < _MIN_LEN:
            continue
        u = (b - a) / length
        n = np.array([-u[1], u[0]])
        half = float(getattr(w, "thickness", 200.0)) / 2.0

        d = W - a
        s, t = d @ u, d @ n
        span = (s > 0) & (s < length)
        at = np.abs(t)
        on = int((span & (np.abs(at - half) < _ON)).sum())
        ctrl = [int((span & (np.abs(at - (half + c)) < _ON)).sum()) for c in _CTRL]
        contrasts.append((on + 1.0) / (float(np.median(ctrl)) + 1.0))
        hits.append(on > 0)

        db = band[:, :2] - a
        sb, tb = db @ u, db @ n
        pair = _peak_pair(tb[(sb > 0) & (sb < length) & (np.abs(tb) < 400.0)])
        if pair is not None:
            biases.append(float(w.thickness) - pair)

    rep.judged = len(contrasts)
    if not contrasts:
        return rep
    rep.contrast_median = float(np.median(contrasts))
    rep.hit_frac = float(np.mean(hits))
    if biases:
        rep.thickness_bias = float(np.median(biases))

    if rep.contrast_median < _CONTRAST_BAD:
        rep.warnings.append(
            f"seinät eivät erotu ympäristöstään (kontrasti {rep.contrast_median:.2f}) "
            "— tässä kohteessa malli on todennäköisesti pääosin virheellinen")
    if rep.hit_frac < _HIT_BAD:
        rep.warnings.append(
            f"vain {rep.hit_frac:.0%} seinistä on oman pintansa päällä "
            "— seinät ovat väärässä paikassa tai paksuus on väärin")
    if rep.thickness_bias is not None and abs(rep.thickness_bias) > _THICK_BAD:
        rep.warnings.append(
            f"paksuus poikkeaa pinnoista mitatusta {rep.thickness_bias:+.0f} mm "
            "— seinätyypit ja määrälaskenta eivät pidä")
    return rep

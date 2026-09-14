"""Oppiminen käyttäjän korjauksista SAMAN projektin sisällä.

Globaali sääntö ei erota kellarin valeseinää aidosta (paras yksittäinen
piirre AUC 0.776), mutta saman rakennuksen omilla korjauksilla koulutettu
yhdistelmä erottaa: 0.866 40 korjauksella ja 0.896 80:llä
(`data/_perproj_curve.py`, käyttäjän 208 labelia).

Tämä EI poista mitään. Automaattinen poisto maksaisi 20 korjauksella 15 %
aidoista seinistä; järjestys ei maksa mitään ja tuo 20 epäilyttävimmän
joukkoon viisinkertaisesti valeseiniä satunnaiseen verrattuna.

Malli ei yleisty rakennuksesta toiseen (mitattu AUC 0.570), joten jokainen
projekti aloittaa tyhjästä.
"""
from __future__ import annotations

import numpy as np

FEATURES = ("len", "logpts", "thick", "conf", "support", "cont", "flat",
            "contrast", "hspan", "htop", "body", "topvar", "cover")
MIN_LABELS = 20
MIN_PER_CLASS = 2


def wall_vector(w) -> np.ndarray | None:
    ev = getattr(w, "evidence", None)
    if not ev:
        return None
    vals = dict(ev, conf=w.confidence, support=w.support, cont=w.continuity)
    return np.array([float(vals.get(k) or 0.0) for k in FEATURES], float)


def _fit(X: np.ndarray, y: np.ndarray, iters: int = 900, lr: float = 0.25,
         l2: float = 0.05):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1])
    b = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Z @ w + b)))
        w -= lr * (Z.T @ (p - y) / len(y) + l2 * w)
        b -= lr * float((p - y).mean())
    return lambda A: 1.0 / (1.0 + np.exp(-(((A - mu) / sd) @ w + b)))


class CorrectionLearner:
    """Kerää korjaukset (aito/vale) ja järjestää loput seinät epäilyn mukaan."""

    def __init__(self) -> None:
        self._rows: dict[str, tuple[list[float], int]] = {}

    def record(self, wall, is_real: bool) -> bool:
        v = wall_vector(wall)
        if v is None:
            return False
        self._rows[wall.id] = (v.tolist(), 1 if is_real else 0)
        return True

    def labelled(self, wall_id: str) -> bool:
        return wall_id in self._rows

    def counts(self) -> tuple[int, int]:
        real = sum(1 for _, y in self._rows.values() if y == 1)
        return real, len(self._rows) - real

    def ready(self) -> bool:
        real, fake = self.counts()
        return (real + fake >= MIN_LABELS and real >= MIN_PER_CLASS
                and fake >= MIN_PER_CLASS)

    def rank(self, walls) -> list[tuple[object, float]]:
        """(seinä, P(aito)) epäilyttävin ensin; tyhjä jos malli ei ole valmis."""
        if not self.ready():
            return []
        X = np.array([v for v, _ in self._rows.values()], float)
        y = np.array([t for _, t in self._rows.values()], float)
        score = _fit(X, y)
        cand = [(w, wall_vector(w)) for w in walls if not self.labelled(w.id)]
        cand = [(w, v) for w, v in cand if v is not None]
        if not cand:
            return []
        p = score(np.array([v for _, v in cand], float))
        order = np.argsort(p, kind="stable")
        return [(cand[i][0], float(p[i])) for i in order]

    def to_json(self) -> dict:
        return {"features": list(FEATURES),
                "rows": {k: {"x": v, "real": y} for k, (v, y) in self._rows.items()}}

    @classmethod
    def from_json(cls, data: dict) -> "CorrectionLearner":
        out = cls()
        if list(data.get("features", [])) != list(FEATURES):
            return out
        for k, r in data.get("rows", {}).items():
            out._rows[k] = (list(r["x"]), int(r["real"]))
        return out

"""Tarkistustyönkulun simulaatio: montako valeseinää löytyy k tarkistuksella?

`_perproj_curve.py` mittaa mallia satunnaisella koulutusjoukolla. Tuotteessa
käyttäjä ei labeloi satunnaisia seiniä vaan tarkistaa listan järjestyksessä,
ja opittu järjestys muuttuu jokaisen korjauksen jälkeen. Tämä ajaa sen
silmukan tuotannon omalla `CorrectionLearner`illa.

Strategiat:
  satunnainen  - tarkistaa seiniä satunnaisessa järjestyksessä
  lista        - nykyinen Tarkistus-lista ensin (flag_low_confidence), sitten satunnainen
  opittu       - kuten lista kunnes malli on valmis, sitten aina epäilyttävin

Käyttö:
  _perproj_sim.py <model.json jossa evidence> <labels.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from ordinate.core.qa.deviation import flag_low_confidence
from ordinate.core.qa.project_learning import CorrectionLearner, wall_vector
from ordinate.schemas.model import StructuralModel

_KS = (10, 20, 40, 60, 80, 120)
_SEEDS = 30


def main(model_json: str, labels_json: str) -> None:
    m = StructuralModel.load(model_json)
    lab = json.loads(Path(labels_json).read_text(encoding="utf-8"))
    pool = [(w, bool(lab[str(i)])) for i, w in enumerate(m.walls)
            if str(i) in lab and wall_vector(w) is not None]
    walls = [w for w, _ in pool]
    truth = {w.id: r for w, r in pool}
    flagged = [f["id"] for f in flag_low_confidence(m) if f["type"] == "wall"]
    flagged = [i for i in flagged if i in truth]
    n_fake = sum(1 for r in truth.values() if not r)
    print(f"{len(pool)} seinää, valeita {n_fake}, Tarkistus-listalla {len(flagged)} "
          f"(joista valeita {sum(1 for i in flagged if not truth[i])})")

    kmax = min(max(_KS), len(pool))
    res = {s: np.zeros((_SEEDS, kmax)) for s in
           ("satunnainen", "lista", "opittu", "opittu+conf", "opittu+tuki")}
    by_conf = sorted((w for w in walls), key=lambda w: (w.confidence, w.id))
    by_sup = sorted((w for w in walls), key=lambda w: (w.support or 0.0, w.id))
    for seed in range(_SEEDS):
        rng = np.random.default_rng(seed)
        rand = [walls[i].id for i in rng.permutation(len(walls))]
        listed = flagged + [i for i in rand if i not in set(flagged)]
        for strat in res:
            learner = CorrectionLearner()
            by_id = {w.id: w for w in walls}
            seen: list[str] = []
            order = {"satunnainen": rand, "lista": listed, "opittu": listed,
                     "opittu+conf": flagged + [w.id for w in by_conf if w.id not in set(flagged)],
                     "opittu+tuki": flagged + [w.id for w in by_sup if w.id not in set(flagged)],
                     }[strat]
            for k in range(kmax):
                nxt = None
                if strat.startswith("opittu") and learner.ready():
                    ranked = learner.rank([by_id[i] for i in by_id if i not in set(seen)])
                    nxt = ranked[0][0].id if ranked else None
                if nxt is None:
                    nxt = next(i for i in order if i not in set(seen))
                seen.append(nxt)
                learner.record(by_id[nxt], truth[nxt])
                res[strat][seed, k] = sum(1 for i in seen if not truth[i])
    ks = [k for k in _KS if k <= kmax]
    print(f"\nvaleseiniä löydetty (/{n_fake}) kun tarkistettu k seinää, ka. {_SEEDS} arvontaa")
    print(f"  {'k':>4}" + "".join(f"  {s:>12}" for s in res))
    for k in ks:
        print(f"  {k:>4}" + "".join(f"  {res[s][:, k - 1].mean():12.1f}" for s in res))


if __name__ == "__main__":
    main(*sys.argv[1:3])

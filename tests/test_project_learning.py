"""Oppiminen käyttäjän korjauksista: järjestys, valmiusehto ja tallennus."""
from __future__ import annotations

import numpy as np

from ordinate.core.qa.project_learning import MIN_LABELS, CorrectionLearner, wall_vector
from ordinate.schemas.model import ElementSource, Wall


def _wall(i: int, fake: bool, rng) -> Wall:
    ev = {k: float(rng.normal(1.0, 0.1)) for k in
          ("len", "logpts", "thick", "contrast", "hspan", "htop", "body", "topvar", "cover")}
    ev["flat"] = float(rng.normal(2.5 if fake else 0.2, 0.2))
    return Wall(id=f"w{i:03d}", confidence=0.9, source=ElementSource(method="contour"),
                axis=[[0.0, i * 1000.0], [3000.0, i * 1000.0]], height=2700.0,
                thickness=120.0, support=0.8, continuity=0.9, evidence=ev)


def _walls(n: int, fake_every: int, seed: int = 0) -> list[Wall]:
    rng = np.random.default_rng(seed)
    return [_wall(i, i % fake_every == 0, rng) for i in range(n)]


def test_not_ready_until_enough_labels_of_both_classes() -> None:
    walls = _walls(60, 4)
    lr = CorrectionLearner()
    for w in walls[:MIN_LABELS - 1]:
        lr.record(w, is_real=int(w.id[1:]) % 4 != 0)
    assert not lr.ready() and lr.rank(walls) == []
    only_real = CorrectionLearner()
    for w in [w for w in walls if int(w.id[1:]) % 4 != 0][:MIN_LABELS + 5]:
        only_real.record(w, is_real=True)
    assert not only_real.ready()


def test_rank_puts_fakes_first_and_skips_labelled() -> None:
    walls = _walls(80, 4)
    lr = CorrectionLearner()
    for w in walls[:24]:
        lr.record(w, is_real=int(w.id[1:]) % 4 != 0)
    ranked = lr.rank(walls)
    ids = [w.id for w, _ in ranked]
    assert len(ids) == 56 and not any(lr.labelled(i) for i in ids)
    top = ids[:14]
    assert all(int(i[1:]) % 4 == 0 for i in top)
    ps = [p for _, p in ranked]
    assert ps == sorted(ps)


def test_wall_without_evidence_is_not_recorded() -> None:
    w = _walls(1, 4)[0].model_copy(update={"evidence": None})
    lr = CorrectionLearner()
    assert wall_vector(w) is None
    assert not lr.record(w, is_real=True)
    assert lr.counts() == (0, 0)


def test_json_round_trip_and_feature_mismatch() -> None:
    walls = _walls(40, 4)
    lr = CorrectionLearner()
    for w in walls[:22]:
        lr.record(w, is_real=int(w.id[1:]) % 4 != 0)
    back = CorrectionLearner.from_json(lr.to_json())
    assert back.counts() == lr.counts() and back.ready()
    assert [w.id for w, _ in back.rank(walls)] == [w.id for w, _ in lr.rank(walls)]
    stale = lr.to_json()
    stale["features"] = ["len"]
    assert CorrectionLearner.from_json(stale).counts() == (0, 0)

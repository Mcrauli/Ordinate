"""Kouluta seinätarkistin ehdokastaulukosta ja vie puut JSONiin.

Aja (.venv-train):
  python export_wall_verifier.py data/output/_cand93.csv models/wall_verifier.json
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ordinate.core.semantics.wall_verifier import FEATURES  # noqa: E402

src, dst = sys.argv[1], sys.argv[2]
R = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r["gtfrac"] not in ("nan", "")]
X = np.array([[float(r[k]) for k in FEATURES] for r in R])
g = np.array([float(r["gtfrac"]) for r in R])
use = (g >= 0.5) | (g <= 0.2)
y = (g >= 0.5).astype(int)
rf = RandomForestClassifier(n_estimators=150, min_samples_leaf=3, class_weight="balanced",
                            random_state=0).fit(X[use], y[use])
trees = []
for est in rf.estimators_:
    t = est.tree_
    v = t.value[:, 0, :]
    p1 = v[:, 1] / np.maximum(v.sum(axis=1), 1e-12)
    trees.append({"left": t.children_left.tolist(), "right": t.children_right.tolist(),
                  "feature": np.maximum(t.feature, 0).tolist(),
                  "threshold": [round(float(x), 6) for x in t.threshold],
                  "value": [round(float(x), 5) for x in p1]})
Path(dst).write_text(json.dumps({"features": FEATURES, "trees": trees, "n_train": int(use.sum())}),
                     encoding="utf-8")
np.save(Path(dst).with_suffix(".check.npy"), np.column_stack([X[:50], rf.predict_proba(X[:50])[:, 1]]))
print(f"{len(trees)} puuta, {int(use.sum())} opetusriviä -> {dst} ({Path(dst).stat().st_size / 1e6:.1f} MB)")

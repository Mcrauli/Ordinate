"""Ehdokastarkistimen koulutus + arvio tyomaa kerrallaan (leave-one-site-out).

Kaytto: _cand_train.py <cand.csv>   (.venv-train, scikit-learn)
"""
import csv
import sys

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

R = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
F = [k for k in R[0] if k not in ("scene", "site", "id", "src", "gtfrac")]
X = np.array([[float(r[k]) for k in F] for r in R])
g = np.array([float(r["gtfrac"]) if r["gtfrac"] not in ("nan", "") else 0.0 for r in R])
site = np.array([r["site"] for r in R])
y = (g >= 0.5).astype(int); use = (g >= 0.5) | (g <= 0.2)
print(f"ehdokkaita {len(R)}, seinia {y[use].sum()}, ei-seinia {(1 - y[use]).sum()}, epaselvia {(~use).sum()}")
models = {
    "rf": lambda: RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced", random_state=0),
    "gb": lambda: GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=0),
    "lr": lambda: LogisticRegression(max_iter=2000, class_weight="balanced"),
}
for name, mk in models.items():
    prob = np.zeros(len(R))
    for s in np.unique(site):
        tr = use & (site != s); te = site == s
        m = mk().fit(X[tr], y[tr])
        prob[te] = m.predict_proba(X[te])[:, 1]
    print(f"\n{name}:")
    for thr in (0.2, 0.3, 0.4, 0.5):
        rej = prob < thr
        print(f"  kynnys {thr}: hylkaa ei-seinia {(rej & use & (y == 0)).sum()}/{(use & (y == 0)).sum()}, "
              f"seinia {(rej & use & (y == 1)).sum()}/{(use & (y == 1)).sum()}  | per tyomaa: " +
              " ".join(f"{s}:{(rej & (site == s) & use & (y == 0)).sum()}-{(rej & (site == s) & use & (y == 1)).sum()}" for s in np.unique(site)))
m = models["rf"]().fit(X[use], y[use])
imp = sorted(zip(m.feature_importances_, F), reverse=True)
print("\ntarkeimmat:", ", ".join(f"{k} {v:.2f}" for v, k in imp[:10]))

if len(sys.argv) > 2:
    prob = np.zeros(len(R))
    for s in np.unique(site):
        tr = use & (site != s); te = site == s
        prob[te] = models["rf"]().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh); wr.writerow(["scene", "id", "src", "prob", "gtfrac"])
        for r, p in zip(R, prob):
            wr.writerow([r["scene"], r["id"], r["src"], round(float(p), 4), r["gtfrac"]])
    print("todennakoisyydet ->", sys.argv[2])

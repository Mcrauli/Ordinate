"""Lisenssivapaat geometriset piirteet per piste (paikallinen PCA / kovarianssi).
Erottaa litteät rakennepinnat (seinä/lattia/katto) mielivaltaisesti
suuntautuneesta kalusteesta/krääsästä pelkällä geometrialla — täydentää
xyz+väriä. Kaikki puhdasta lineaarialgebraa (Weinmann et al. -tyyliset
dimensionaalisuuspiirteet), ei mallilisenssiä.

Palauttaa (N,3): [verticality, planarity, sphericity] ∈ [0,1].
  verticality = 1-|n_z|  (0 vaakapinta lattia/katto, 1 pystyseinä)
  planarity   = (λ2-λ3)/λ1  (korkea tasomaisille pinnoille)
  sphericity  = λ3/λ1       (korkea volyymikalusteelle/krääsälle)
λ1≥λ2≥λ3 = paikallisen naapuruston kovarianssin ominaisarvot.
"""
import numpy as np
from scipy.spatial import cKDTree


def compute(xyz: np.ndarray, k: int = 16) -> np.ndarray:
    xyz = np.ascontiguousarray(xyz[:, :3].astype(np.float64))
    n = len(xyz)
    if n < k + 1:
        return np.zeros((n, 3), np.float32)
    tree = cKDTree(xyz)
    _, idx = tree.query(xyz, k=k, workers=-1)          # (N,k) itse mukana
    nb = xyz[idx]                                       # (N,k,3)
    nb = nb - nb.mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / k         # (N,3,3)
    ev = np.linalg.eigvalsh(cov)                        # nouseva λ3,λ2,λ1
    l3, l2, l1 = ev[:, 0], ev[:, 1], ev[:, 2]
    l1 = np.maximum(l1, 1e-12)
    planarity = (l2 - l3) / l1
    sphericity = l3 / l1
    # normaali = pienimmän ominaisarvon vektori → sen z-komponentti
    evec = np.linalg.eigh(cov)[1][:, :, 0]             # (N,3) pienin
    verticality = 1.0 - np.abs(evec[:, 2])
    out = np.column_stack([verticality, planarity, sphericity]).astype(np.float32)
    return np.clip(out, 0.0, 1.0)

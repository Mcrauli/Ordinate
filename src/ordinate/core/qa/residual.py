"""Selittääkö malli pisteen — 3D-tarkastuksen residuaali.

Ajetaan 3D-tarkastuksen aliprosessissa (`ordinate-cli viewcloud --model`),
ei ikkunan prosessissa: 1.5 M pistettä × 260 seinää on sekunteja numpy-työtä,
ja ikkunaprosessissa se kaatui toistuvasti muistin suojausvirheeseen heti
näytönohjaimen latauksen jälkeen.
"""
from __future__ import annotations

import numpy as np


def classify_explained(P: np.ndarray, model: dict, tol: float = 200.0) -> np.ndarray:
    P = np.asarray(P, float)
    expl = np.zeros(len(P), bool)
    xy, z = P[:, :2], P[:, 2]
    for w in model["walls"]:
        (x0, y0), (x1, y1) = w["axis"][0], w["axis"][1]
        d = np.array([x1 - x0, y1 - y0]); L = float(np.hypot(*d))
        if L < 1:
            continue
        u = d / L; n = np.array([-u[1], u[0]])
        rel = xy - np.array([x0, y0]); along = rel @ u; perp = rel @ n
        z0 = w.get("z_min", 0.0); z1 = z0 + w["height"]; th = w.get("thickness", 100.0)
        expl |= ((np.abs(perp) < th / 2 + tol) & (along >= -tol) & (along <= L + tol)
                 & (z >= z0 - tol) & (z <= z1 + tol))
    for c in model.get("columns", []):
        cx, cy = c["location"]; z0 = c["base_z"]; z1 = z0 + c["height"]; pr = c["profile"]
        expl |= ((np.abs(xy[:, 0] - cx) < pr["width"] / 2 + tol)
                 & (np.abs(xy[:, 1] - cy) < pr["depth"] / 2 + tol)
                 & (z >= z0 - tol) & (z <= z1 + tol))
    for b in model.get("beams", []):
        a, cc = np.array(b["axis"][0], float), np.array(b["axis"][1], float)
        d = cc - a; L = float(np.linalg.norm(d[:2]))
        if L < 1:
            continue
        u = d[:2] / L; nn = np.array([-u[1], u[0]])
        rel = xy - a[:2]; along = rel @ u; perp = rel @ nn
        pr = b["profile"]; zc = (a[2] + cc[2]) / 2
        expl |= ((np.abs(perp) < pr["width"] / 2 + tol) & (along >= -tol) & (along <= L + tol)
                 & (np.abs(z - zc) < pr["height"] / 2 + tol))
    return expl

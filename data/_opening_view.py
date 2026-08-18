"""Aukot kuvana: mallin seinat + mallin aukot + GT-aukkoinstanssit.

`_opening_qa.py` kertoo etta 3/4 GT-aukoista jaa loytymatta, mutta ei sita
ONKO NIIDEN SEINA MALLISSA. Jos aukko on seinalla jota ei ole mallinnettu, vika
ei ole aukkodetektorissa. Tama piirtaa molemmat samaan pohjaan ja tulostaa
jokaiselle lyhentyneelle GT-aukolle etaisyyden lahimpaan MALLIN seinaan.

Ajo: _opening_view.py <model.json> <coord.npy> <class.npy> [out.png]
"""
from __future__ import annotations

import json
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

_OPEN = (7, 12, 13, 14)
_TOL = 700.0
_MIN_PTS = 500


def main(mj: str, coord_npy: str, class_npy: str, out: str | None = None) -> None:
    m = json.loads(pathlib.Path(mj).read_text(encoding="utf-8"))
    P = np.load(coord_npy).astype(np.float64)
    C = np.load(class_npy).ravel()
    if np.ptp(P[:, 0]) < 500.0:
        P *= 1000.0
    I = np.load(pathlib.Path(class_npy).with_name("instance.npy")).ravel()
    gt = np.isin(C, _OPEN)

    inst = []
    for i in np.unique(I[gt]):
        q = P[gt][I[gt] == i]
        if len(q) < _MIN_PTS:
            continue
        inst.append((int(i), q[:, :2].mean(0), len(q),
                     float(np.hypot(*(q[:, :2].max(0) - q[:, :2].min(0))))))

    walls = {w["id"]: w for w in m["walls"]}
    det = []
    for o in m["openings"]:
        w = walls.get(o["wall_id"])
        if w is None:
            continue
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        u = (b - a) / L
        s0 = o["position_along"]
        det.append((o, a + u * s0, a + u * (s0 + o["width"])))

    def wall_dist(p):
        best = 1e12
        for w in m["walls"]:
            a = np.array(w["axis"][0], float)
            b = np.array(w["axis"][1], float)
            L = float(np.linalg.norm(b - a))
            if L < 1.0:
                continue
            u = (b - a) / L
            s = float(np.clip((p - a) @ u, 0.0, L))
            best = min(best, float(np.linalg.norm(p - (a + u * s))))
        return best

    fig, ax = plt.subplots(figsize=(14, 12))
    for w in m["walls"]:
        a, b = np.array(w["axis"][0], float), np.array(w["axis"][1], float)
        ax.plot([a[0], b[0]], [a[1], b[1]], "-", color="0.55", lw=1.4, zorder=1)
    for o, p0, p1 in det:
        col = "tab:blue" if o["opening_type"] == "door" else "tab:cyan"
        ax.plot([p0[0], p1[0]], [p0[1], p1[1]], "-", color=col, lw=5, zorder=3)

    near, far = 0, 0
    print(f"{'inst':>6s} {'n':>7s} {'leveys':>7s} {'et. mallin aukkoon':>19s} "
          f"{'et. mallin seinaan':>19s}  paatelma")
    for i, c, n, w in sorted(inst, key=lambda t: -t[2]):
        d_op = min((float(np.linalg.norm(0.5 * (p0 + p1) - c)) for _, p0, p1 in det),
                   default=1e12)
        d_w = wall_dist(c)
        ok = d_op <= max(_TOL, w / 2.0)
        why = "OK" if ok else ("SEINA PUUTTUU" if d_w > 500.0 else "seina on, aukko ei")
        if not ok:
            (far if d_w > 500.0 else near).__class__  # ei sivuvaikutusta
            if d_w > 500.0:
                far += 1
            else:
                near += 1
        ax.plot(*c, "o", ms=6 + 6 * (n > 3000),
                color=("tab:green" if ok else ("tab:red" if d_w <= 500 else "tab:orange")),
                zorder=4)
        print(f"{i:6d} {n:7,} {w:7.0f} {d_op:19.0f} {d_w:19.0f}  {why}")

    ax.set_aspect("equal")
    ax.set_title(f"Aukot: harmaa=seina, sininen=mallin aukko, vihrea=GT loytyi, "
                 f"punainen=GT seinalla mutta ei loydetty ({near}), "
                 f"oranssi=GT ilman seinaa ({far})")
    out = out or str(pathlib.Path(mj).with_name("_opening_view.png"))
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"\nGT-aukkoja {len(inst)}  loytyi {len(inst) - near - far}  "
          f"seina mallissa mutta aukko ei {near}  seina puuttuu {far}")
    print(f"kuva: {out}")


if __name__ == "__main__":
    main(*sys.argv[1:5])

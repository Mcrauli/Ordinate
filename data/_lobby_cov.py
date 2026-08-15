"""Aulan A/B kahdesta suunnasta — ilman GT:tä, pilvi ainoana tuomarina.

TUKI (mediaani) kertoo osuuko malli pintaan = tarkkuuden suunta.
LUNASTETTU osuus kertoo kuinka suuri osa vyötärökaistan pisteistä on jonkin
mallin seinän kaistassa = kattavuuden suunta. Absoluuttiluku on merkityksetön
(kaistassa on myös liukuportaat ja kalusteet), mutta kahden mallin VERTAILU
samalla pilvellä on rehellinen, koska nimittäjä on sama.

Ajo: .venv/Scripts/python.exe data/_lobby_cov.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import OUTPUT  # noqa: E402

_BAND = 150.0     # mm — kuinka läheltä piste lasketaan seinän lunastamaksi


def claimed(m, pts) -> tuple[float, float]:
    xy = pts[:, :2]
    hit = np.zeros(len(xy), bool)
    total_len = 0.0
    for w in m["walls"]:
        a = np.array(w["axis"][0], float)
        b = np.array(w["axis"][1], float)
        L = float(np.linalg.norm(b - a))
        if L < 1.0:
            continue
        total_len += L
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        d = xy - a
        s, t = d @ u, d @ n
        half = float(w["thickness"]) / 2.0
        hit |= (s > 0) & (s < L) & (np.abs(np.abs(t) - half) < _BAND)
    return float(hit.mean()), total_len / 1000.0


def main() -> None:
    pts = np.load("data/_lobby_band.npy")
    print(f"vyötärökaista {len(pts):,} pistettä\n")
    print(f"{'malli':10s} {'seiniä':>7s} {'pituus':>9s} {'tuki med':>9s} "
          f"{'jatk med':>9s} {'lunastettu':>11s}")
    for tag in ("auto", "contour"):
        mj = Path(str(OUTPUT / f"_lobbyab_{tag}")) / "floor_00" / "model.json"
        m = json.loads(mj.read_text(encoding="utf-8"))
        sup = [w["support"] for w in m["walls"] if w.get("support") is not None]
        con = [w["continuity"] for w in m["walls"] if w.get("continuity") is not None]
        frac, tl = claimed(m, pts)
        print(f"{tag:10s} {len(m['walls']):7d} {tl:8.1f}m {np.median(sup):9.2f} "
              f"{np.median(con):9.2f} {frac:11.3f}")

    print("\nheikoimmat seinät (tuki < 0.25) — nämä ovat kuvan irralliset viivat:")
    for tag in ("auto", "contour"):
        mj = Path(str(OUTPUT / f"_lobbyab_{tag}")) / "floor_00" / "model.json"
        m = json.loads(mj.read_text(encoding="utf-8"))
        weak = [(w["id"], w["support"], float(np.linalg.norm(
            np.array(w["axis"][1], float) - np.array(w["axis"][0], float))) / 1000.0)
            for w in m["walls"] if (w.get("support") or 1.0) < 0.25]
        tot = sum(x[2] for x in weak)
        print(f"  {tag:8s} {len(weak)} kpl, yhteensä {tot:.1f} m: "
              + ", ".join(f"{i}({s:.2f}, {L:.1f}m)" for i, s, L in weak))


if __name__ == "__main__":
    main()

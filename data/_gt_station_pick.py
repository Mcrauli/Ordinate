"""Mitka keilausasemat kannattaa labeloida CloudComparessa?

Koko kellari on 27 asemaa ja liian raskas segmentoitavaksi. GT:ta ei tarvita
kaikkialle: sen tehtava on ratkaista ne paatokset jotka ovat nyt arvauksia.
Kellarissa se on tarkkuus (0.204) — onko mallinnettu seina aito seina vai
kohta putkimetsassa. Ne seinat tunnistaa MALLIN OMISTA luvuista: matala tuki
ja matala jatkuvuus tarkoittavat etta mikaan ei todista seinaa oikeaksi.

Asemien origot luetaan E57:n headerista (`scanner_origins`) — pisteita ei
ladata, joten 27 aseman lapikaynti maksaa sekunteja eika minuutteja.

Valinta on ahne peitto: ota asema joka kattaa eniten viela kattamatonta
kiistanalaista seinapituutta. Kaksi vierekkaista asemaa nakee saman seinan,
eika sama seina labeloituna kahdesti kerro mitaan uutta.

Kaytto: _gt_station_pick.py <model.json> <e57-hakemisto> [sade_mm] [n]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ordinate.core.geometry.loader import scanner_origins  # noqa: E402

_SUPPORT_Q = 25.0      # tuen alakvartiili MALLIN OMASTA jakaumasta


def _walls(model_json: Path):
    import json
    d = json.loads(model_json.read_text(encoding="utf-8"))
    out = []
    for w in d["walls"]:
        a, b = np.asarray(w["axis"][0], float), np.asarray(w["axis"][1], float)
        out.append({"id": w["id"], "a": a[:2], "b": b[:2],
                    "len": float(np.linalg.norm(b[:2] - a[:2])),
                    "sup": w.get("support")})
    have = [w["sup"] for w in out if w["sup"] is not None]
    cut = float(np.percentile(have, _SUPPORT_Q)) if have else 0.0
    for w in out:
        w["suspect"] = w["sup"] is None or w["sup"] < cut
    return out, cut


def _seg_dist(p, a, b):
    ab = b - a
    L2 = float(ab @ ab)
    t = 0.0 if L2 == 0 else float(np.clip((p - a) @ ab / L2, 0.0, 1.0))
    return float(np.linalg.norm(p - (a + t * ab)))


def main(model_json: str, e57_dir: str, radius: str = "8000", n: str = "3") -> None:
    walls, cut = _walls(Path(model_json))
    R, N = float(radius), int(n)
    total_m = sum(w["len"] for w in walls) / 1000.0
    weak_m = sum(w["len"] for w in walls if w["suspect"]) / 1000.0
    print(f"{len(walls)} seinaa, {total_m:.0f} m; heikoin neljannes "
          f"(tuki < {cut:.3f}) {weak_m:.0f} m")

    stations = []
    for f in sorted(Path(e57_dir).glob("*.e57")):
        try:
            origs = scanner_origins(f)
        except Exception as exc:  # noqa: BLE001
            print(f"  {f.name}: pose ei luettavissa ({exc})")
            continue
        for k, o in enumerate(origs):
            stations.append((f.name if len(origs) == 1 else f"{f.name}#{k}",
                             np.asarray(o, float)[:2]))
    if not stations:
        print("Yhdellakaan asemalla ei ole poseta — valintaa ei voi tehda.")
        return

    # `scanner_origins` skaalaa metrit millimetreiksi vain jos origon NORMI on
    # alle 200 — se on rakennuksen SIJAINTI, ei sen yksikko. Paikallisessa
    # ruudukossa (kellari ~200 m, 541 m) ehto ei laukea ja origot jaavat
    # metreiksi. Yksikko luetaan siita kumpi kerroin osuu mallin alueelle.
    ax = np.array([w["a"] for w in walls] + [w["b"] for w in walls])
    lo, hi = ax.min(axis=0), ax.max(axis=0)

    def _inside(mult: float) -> int:
        return sum(1 for _, o in stations
                   if lo[0] <= o[0] * mult <= hi[0] and lo[1] <= o[1] * mult <= hi[1])

    hits = {m: _inside(m) for m in (1.0, 1000.0)}
    mult = max(hits, key=lambda m: hits[m])
    print(f"{len(stations)} asemaa, {hits[mult]} mallin jalanjaljen sisalla "
          f"(kerroin {mult:.0f}, sade {R/1000:.0f} m)")
    if hits[mult] == 0:
        print("VAROITUS: yksikaan asema ei osu mallin alueelle kummallakaan "
              "kertoimella — ala luota alla oleviin.")
        return
    stations = [(n, o * mult) for n, o in stations]

    seen = {}
    for name, o in stations:
        seen[name] = {i for i, w in enumerate(walls)
                      if _seg_dist(o, w["a"], w["b"]) <= R}


    covered: set[int] = set()
    print()
    print(f"{'#':2s} {'asema':30s} {'uutta m':>8s} {'yht m':>7s} {'osuus':>6s} "
          f"{'heikkoa m':>10s}")
    for step in range(N):
        best, gain = None, -1.0
        for name, ids in seen.items():
            g = sum(walls[i]["len"] for i in ids - covered) / 1000.0
            if g > gain:
                best, gain = name, g
        if best is None or gain <= 0.0:
            break
        covered |= seen[best]
        got = sum(walls[i]["len"] for i in covered) / 1000.0
        weak = sum(walls[i]["len"] for i in covered if walls[i]["suspect"]) / 1000.0
        print(f"{step+1:<2d} {best:30s} {gain:8.0f} {got:7.0f} "
              f"{got/total_m if total_m else 0:6.2f} {weak:10.0f}")
        del seen[best]


if __name__ == "__main__":
    main(*sys.argv[1:])

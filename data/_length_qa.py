"""PITUUSMITTARI (seinän pituus = nurkkien etäisyys, +-1.5mm tavoite).

Johdetaan _corner_qa.json:sta: seinän pituus = sen kahden ääri-nurkan etäisyys.
GT = pilvi-sovitettujen keskilinjojen leikkausten etäisyys; malli = mallin
akselileikkausten etäisyys. Kulmavirheet kumoutuvat erotuksessa → pituus on
robustimpi kuin absoluuttinen nurkkasijainti.

Vaatii ajetun data/_corner_qa.py:n.
Aja:  .venv/Scripts/python data/_length_qa.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(r"C:\Users\lauri\scan2bim")
CQ = ROOT / "data" / "_corner_qa.json"


def main() -> None:
    rows = json.loads(CQ.read_text())
    # kerää per seinä: lista (model_corner, gt_corner, both_two_sided)
    by_wall: dict[str, list] = {}
    for r in rows:
        for wid in (r["wi"], r["wj"]):
            by_wall.setdefault(wid, []).append(
                (np.array(r["model_corner"]), np.array(r["gt_corner"]), r["both_two_sided"]))

    errs = []
    ts_errs = []
    for wid, corners in by_wall.items():
        if len(corners) < 2:
            continue
        # ääripäät: kaksi kauimpana toisistaan olevaa MALLI-nurkkaa
        best = (-1.0, None, None)
        for i in range(len(corners)):
            for j in range(i + 1, len(corners)):
                d = float(np.linalg.norm(corners[i][0] - corners[j][0]))
                if d > best[0]:
                    best = (d, corners[i], corners[j])
        _, a, b = best
        m_len = float(np.linalg.norm(a[0] - b[0]))
        g_len = float(np.linalg.norm(a[1] - b[1]))
        if m_len < 300.0:
            continue
        e = abs(m_len - g_len)
        errs.append(e)
        if a[2] and b[2]:
            ts_errs.append(e)

    def stat(name, vals):
        if not vals:
            print(f"  {name}: ei dataa")
            return
        a = np.array(vals)
        print(f"  {name}: mediaani={np.median(a):.2f}mm  keski={a.mean():.2f}mm  "
              f"<1.5mm={100*np.mean(a<1.5):.0f}%  <5mm={100*np.mean(a<5):.0f}%  "
              f"<15mm={100*np.mean(a<15):.0f}%  (n={len(a)})")

    print("PITUUSMITTARI (mallin nurkkaväli vs pilvi-nurkkaväli)")
    stat("PITUUSVIRHE (kaikki)", errs)
    stat("PITUUSVIRHE (2-puoliset nurkat)", ts_errs)


if __name__ == "__main__":
    main()

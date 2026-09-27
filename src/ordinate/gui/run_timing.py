"""Ajon kesto käyttäjälle: juokseva kello ja pisimmät vaiheet.

Diagnostiikka on kirjannut vaiheajat aina, mutta käyttöliittymä ei näyttänyt
niistä mitään — 56 minuutin ajon aikana ei tiennyt oliko mennyt viisi vai
viisikymmentä minuuttia, eikä lopuksi sitä mihin aika meni.

Vaiheen kesto = aika sen aloitusviestistä seuraavaan viestiin. Viestit
ilmoittavat vaiheen ALKAVAN ("Semanttinen suodatin (28 M pistettä)…"), joten
väli seuraavaan on juuri se vaihe.
"""
from __future__ import annotations


def fmt_duration(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def clock(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def slowest_steps(marks: list[tuple[float, str]], total: float, n: int = 3,
                  min_seconds: float = 30.0) -> list[tuple[str, float]]:
    """(viesti, kesto) pisimmästä alkaen. `marks` = (sekunnit alusta, viesti)."""
    steps: list[tuple[str, float]] = []
    for i, (t, msg) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else total
        dur = end - t
        if dur >= min_seconds:
            label = msg.strip().rstrip("…").rstrip(".")
            if len(label) > 60:
                label = label[:57] + "…"
            steps.append((label, dur))
    steps.sort(key=lambda x: -x[1])
    return steps[:n]

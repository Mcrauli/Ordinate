"""Tilojen johtaminen seinä- ja laattarajoista.

Strategia v1: yksinkertainen — lattiarajoista yksi Space per kerros.
  1. Kerätään lattialaatat (floor) ja katot (ceiling/roof).
  2. Yhdistetään lattia + korkein kattolaatat → huonekorkeus.
  3. Käytetään lattian konveksihullua tilan rajauksena.

Strategia v2 (tuleva): flood-fill 2D-ruudukkoon seinäakselien perusteella.
"""
from __future__ import annotations

import uuid
import logging

import numpy as np

from scan2bim.schemas.model import StructuralModel, Space, Slab, ElementSource

log = logging.getLogger(__name__)


def derive_spaces(model: StructuralModel) -> list[Space]:
    """Johda tilat StructuralModelin seinä- ja laattadatasta."""
    floors = [s for s in model.slabs if s.slab_type == "floor"]
    ceilings = [s for s in model.slabs if s.slab_type in ("ceiling", "roof")]

    if not floors:
        log.info("derive_spaces: ei lattioita → ei tiloja")
        return []

    spaces: list[Space] = []

    for floor in floors:
        floor_z = floor.elevation

        # Etsi kattolaatat tämän lattian yläpuolelta — valitse korkein
        above = [c for c in ceilings if c.elevation > floor_z + 500.0]
        if above:
            ceiling_z = float(max(c.elevation for c in above))
        else:
            # Fallback: laske seinien maksimikorkeus
            wall_max_z = _wall_max_z(model, floor_z)
            ceiling_z = wall_max_z if wall_max_z > floor_z + 500 else floor_z + 2800.0

        # Tilan raja = lattian konveksihullu
        # (seinistä tarkennetaan v2:ssa)
        boundary = floor.boundary
        if len(boundary) < 4:
            continue

        confidence = round(min(1.0, floor.confidence * 0.9), 3)
        spaces.append(
            Space(
                id=str(uuid.uuid4()),
                confidence=confidence,
                source=ElementSource(method="z_histogram"),
                boundary=boundary,
                floor_z=round(float(floor_z), 1),
                ceiling_z=round(float(ceiling_z), 1),
            )
        )
        log.info(
            "Tila: lattia z=%.0f mm, katto z=%.0f mm, korkeus %.0f mm",
            floor_z, ceiling_z, ceiling_z - floor_z,
        )

    log.info("derive_spaces: %d tilaa johdettu", len(spaces))
    return spaces


def _wall_max_z(model: StructuralModel, floor_z: float) -> float:
    """Palauttaa seinien maksimikorkeus lattian tasolta."""
    if not model.walls:
        return floor_z + 2800.0
    return float(max(w.height for w in model.walls)) + floor_z

"""
StructuralModel — sisäinen schema josta kaikki export johdetaan.
Jokainen putken vaihe lukee/kirjoittaa tätä: pistepilvi → elementit → IFC/DXF.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Yhteinen kanta
# ---------------------------------------------------------------------------

class ElementSource(BaseModel):
    method: Literal["ransac", "density", "z_histogram", "cluster", "manual", "normals", "floorplan", "opening"]
    plane_ids: list[int] = Field(default_factory=list)
    notes: str = ""


class Element(BaseModel):
    id: str
    confidence: float = Field(ge=0.0, le=1.0)
    classification: str
    source: ElementSource


# ---------------------------------------------------------------------------
# Elementtityypit
# ---------------------------------------------------------------------------

class Wall(Element):
    """Seinä — axis-based, kartoittuu suoraan IfcWall:iin."""
    classification: str = "wall"
    axis: list[list[float]]          # [[x0,y0], [x1,y1]] mm
    height: float                    # mm
    thickness: float                 # mm
    z_min: float = 0.0               # mm — seinän alin piste (lattiaan vertailua varten)


class Slab(Element):
    """Laatta (lattia tai katto)."""
    classification: str = "slab"
    slab_type: Literal["floor", "ceiling", "roof"]
    boundary: list[list[float]]      # [[x,y], ...] mm, suljettu polygoni
    elevation: float                 # mm, z-koordinaatti yläpinnalle
    thickness: float                 # mm


class ColumnProfile(BaseModel):
    shape: Literal["rect", "circle"]
    width: float                     # mm
    depth: float                     # mm (== width jos circle)


class Column(Element):
    """Pilari."""
    classification: str = "column"
    location: list[float]            # [x, y] mm
    base_z: float                    # mm
    height: float                    # mm
    profile: ColumnProfile


class BeamProfile(BaseModel):
    width: float                     # mm
    height: float                    # mm


class Beam(Element):
    """Palkki."""
    classification: str = "beam"
    axis: list[list[float]]          # [[x0,y0,z0], [x1,y1,z1]] mm
    profile: BeamProfile


class Opening(Element):
    """Aukko (ovi tai ikkuna) seinässä."""
    classification: str = "opening"
    opening_type: Literal["door", "window", "unknown"]
    wall_id: str
    position_along: float            # mm — sijainti seinän p0:sta
    width: float                     # mm
    sill_height: float               # mm lattian yläpuolella
    opening_height: float            # mm


class Space(Element):
    """Tila (IfcSpace) — johdettu seinä/laattarajoista."""
    classification: str = "space"
    boundary: list[list[float]]      # [[x,y], ...] mm
    floor_z: float                   # mm
    ceiling_z: float                 # mm


# ---------------------------------------------------------------------------
# Hylätty krääsä (kalusteet/LVI) — kirjataan läpinäkyvyyttä varten
# ---------------------------------------------------------------------------

class Discarded(BaseModel):
    clutter_cluster_count: int = 0
    total_points: int = 0
    reason: str = "furniture/LVI filtered by rule-based clutter detection"


# ---------------------------------------------------------------------------
# Pääschema
# ---------------------------------------------------------------------------

class Metadata(BaseModel):
    units: Literal["mm", "m"] = "mm"
    source_file: str = ""
    voxel_size: float = 20.0         # mm
    detector_method: str = ""
    floor_index: int | None = None   # monikerrosajossa: kerroksen indeksi
    floor_count: int | None = None   # monikerrosajossa: kerrosten määrä


class StructuralModel(BaseModel):
    walls: list[Wall] = Field(default_factory=list)
    slabs: list[Slab] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    columns: list[Column] = Field(default_factory=list)
    beams: list[Beam] = Field(default_factory=list)
    spaces: list[Space] = Field(default_factory=list)
    discarded: Discarded = Field(default_factory=Discarded)
    metadata: Metadata = Field(default_factory=Metadata)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "StructuralModel":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def summary(self) -> str:
        return (
            f"StructuralModel: {len(self.walls)} walls, {len(self.slabs)} slabs, "
            f"{len(self.openings)} openings "
            f"({sum(1 for o in self.openings if o.opening_type == 'door')} doors, "
            f"{sum(1 for o in self.openings if o.opening_type == 'window')} windows), "
            f"{len(self.columns)} columns, {len(self.beams)} beams, "
            f"{len(self.spaces)} spaces | discarded={self.discarded.clutter_cluster_count} clusters"
        )

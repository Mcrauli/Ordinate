"""IFC4-kirjoitus: StructuralModel → .ifc

Hierarkia: IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey
Seinät:    IfcWall, axis-based + SweptSolid body (IfcRectangleProfileDef)
Laatat:    IfcSlab, arbitrary closed profile + SweptSolid body
Yksiköt:   mm (IfcSIUnit MILLI METRE)
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import ifcopenshell
import ifcopenshell.guid

from scan2bim.schemas.model import StructuralModel, Wall, Slab, Space, Column, Beam, Opening


def write_ifc(model: StructuralModel, path: Path) -> None:
    ifc = _build_project_skeleton()
    oh = ifc.by_type("IfcOwnerHistory")[0]
    storey = ifc.by_type("IfcBuildingStorey")[0]
    body_ctx = next(
        c for c in ifc.by_type("IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Body"
    )
    axis_ctx = next(
        c for c in ifc.by_type("IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Axis"
    )

    elements: list[ifcopenshell.entity_instance] = []

    openings_by_wall = _openings_by_wall(model)
    for w in model.walls:
        wall_ent = _create_wall(ifc, w, oh, body_ctx, axis_ctx)
        elements.append(wall_ent)
        for op in openings_by_wall.get(w.id, []):
            elements.extend(_create_opening(ifc, wall_ent, w, op, oh, body_ctx))

    for b in model.beams:
        e = _create_beam(ifc, b, oh, body_ctx)
        if e is not None:
            elements.append(e)

    for c in model.columns:
        e = _create_column(ifc, c, oh, body_ctx)
        if e is not None:
            elements.append(e)

    for s in model.slabs:
        e = _create_slab(ifc, s, oh, body_ctx)
        if e is not None:
            elements.append(e)

    space_entities: list[ifcopenshell.entity_instance] = []
    for sp in model.spaces:
        e = _create_space(ifc, sp, oh, body_ctx)
        if e is not None:
            space_entities.append(e)

    if space_entities:
        ifc.createIfcRelContainedInSpatialStructure(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=oh,
            RelatedElements=space_entities,
            RelatingStructure=storey,
        )

    if elements:
        ifc.createIfcRelContainedInSpatialStructure(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=oh,
            RelatedElements=elements,
            RelatingStructure=storey,
        )

    ifc.write(str(path))


def _floor_elevation(model: StructuralModel) -> float:
    """Kerroksen korkeus: alin lattialaatta, muuten 0."""
    floor_slabs = [s.elevation for s in model.slabs if getattr(s, "slab_type", "") == "floor"]
    return float(min(floor_slabs)) if floor_slabs else 0.0


def write_building_ifc(models: list[StructuralModel], path: Path) -> None:
    """Yksi IFC, jossa kaikki kerrokset omina IfcBuildingStorey-tasoinaan.
    Käyttää samaa elementtikirjoitusta kuin write_ifc — koko talomalli Solibriin."""
    models = [m for m in models if m is not None]
    if not models:
        return
    models = sorted(models, key=lambda m: (m.metadata.floor_index or 0))

    ifc = _build_project_skeleton()
    oh = ifc.by_type("IfcOwnerHistory")[0]
    building = ifc.by_type("IfcBuilding")[0]
    base_storey = ifc.by_type("IfcBuildingStorey")[0]
    body_ctx = next(
        c for c in ifc.by_type("IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Body"
    )
    axis_ctx = next(
        c for c in ifc.by_type("IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Axis"
    )

    for i, model in enumerate(models):
        if i == 0:
            storey = base_storey
        else:
            storey = ifc.createIfcBuildingStorey(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
                CompositionType="ELEMENT",
            )
            ifc.createIfcRelAggregates(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
                RelatingObject=building, RelatedObjects=[storey],
            )
        idx = model.metadata.floor_index if model.metadata.floor_index is not None else i
        storey.Name = f"Kerros {idx + 1}"
        storey.Elevation = _floor_elevation(model)

        elements: list[ifcopenshell.entity_instance] = []
        openings_by_wall = _openings_by_wall(model)
        for w in model.walls:
            wall_ent = _create_wall(ifc, w, oh, body_ctx, axis_ctx)
            elements.append(wall_ent)
            for op in openings_by_wall.get(w.id, []):
                elements.extend(_create_opening(ifc, wall_ent, w, op, oh, body_ctx))
        for b in model.beams:
            e = _create_beam(ifc, b, oh, body_ctx)
            if e is not None:
                elements.append(e)
        for c in model.columns:
            e = _create_column(ifc, c, oh, body_ctx)
            if e is not None:
                elements.append(e)
        for s in model.slabs:
            e = _create_slab(ifc, s, oh, body_ctx)
            if e is not None:
                elements.append(e)

        spaces: list[ifcopenshell.entity_instance] = []
        for sp in model.spaces:
            e = _create_space(ifc, sp, oh, body_ctx)
            if e is not None:
                spaces.append(e)

        if spaces:
            ifc.createIfcRelContainedInSpatialStructure(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
                RelatedElements=spaces, RelatingStructure=storey,
            )
        if elements:
            ifc.createIfcRelContainedInSpatialStructure(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
                RelatedElements=elements, RelatingStructure=storey,
            )

    ifc.write(str(path))


# --------------------------------------------------------------------------- #
# Projekti-skeleton
# --------------------------------------------------------------------------- #

def _build_project_skeleton() -> ifcopenshell.file:
    ifc = ifcopenshell.file(schema="IFC4")
    oh = _make_owner_history(ifc)

    mm_unit = ifc.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    units = ifc.createIfcUnitAssignment(Units=[mm_unit])

    wcs = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    ctx = ifc.createIfcGeometricRepresentationContext(
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=wcs,
    )
    body_ctx = ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=ctx,
        TargetView="MODEL_VIEW",
    )
    ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Axis",
        ContextType="Model",
        ParentContext=ctx,
        TargetView="GRAPH_VIEW",
    )

    project = ifc.createIfcProject(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name="scan2bim",
        UnitsInContext=units,
        RepresentationContexts=[ctx],
    )
    site = ifc.createIfcSite(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name="Site",
        CompositionType="ELEMENT",
    )
    building = ifc.createIfcBuilding(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name="Building",
        CompositionType="ELEMENT",
    )
    storey = ifc.createIfcBuildingStorey(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name="Storey 1",
        CompositionType="ELEMENT",
        Elevation=0.0,
    )

    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatingObject=project, RelatedObjects=[site],
    )
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatingObject=site, RelatedObjects=[building],
    )
    ifc.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatingObject=building, RelatedObjects=[storey],
    )

    return ifc


def _make_owner_history(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance:
    org = ifc.createIfcOrganization(Name="scan2bim")
    person = ifc.createIfcPerson(FamilyName="Rekola", GivenName="Lauri")
    p_and_o = ifc.createIfcPersonAndOrganization(ThePerson=person, TheOrganization=org)
    app = ifc.createIfcApplication(
        ApplicationDeveloper=org,
        Version="0.1.0",
        ApplicationFullName="scan2bim",
        ApplicationIdentifier="scan2bim",
    )
    return ifc.createIfcOwnerHistory(
        OwningUser=p_and_o,
        OwningApplication=app,
        ChangeAction="NOTDEFINED",
        CreationDate=int(time.time()),
    )


# --------------------------------------------------------------------------- #
# Seinä-entiteetti
# --------------------------------------------------------------------------- #

def _create_wall(
    ifc: ifcopenshell.file,
    wall: Wall,
    oh: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
    axis_ctx: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance:
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    vec = p1 - p0
    length = float(np.linalg.norm(vec))
    if length < 1.0:
        length = 1.0
        vec = np.array([1.0, 0.0])
    else:
        vec = vec / length

    mid = (p0 + p1) / 2.0
    half = length / 2.0

    # Placement: origin at midpoint + seinän todellinen alakorkeus (z_min).
    # Ilman z_min:iä seinät jäisivät z=0:aan ja erkanisivat laatoista/pilareista
    # (jotka sijoitetaan oikeaan korkeuteensa) — varsinkin oikeilla koordinaateilla.
    placement = _axis2placement(
        ifc,
        origin=[float(mid[0]), float(mid[1]), float(wall.z_min)],
        x_dir=[float(vec[0]), float(vec[1]), 0.0],
    )

    # Axis repr: 2D centerline [-half, 0] → [+half, 0] in local coords
    axis_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=axis_ctx,
        RepresentationIdentifier="Axis",
        RepresentationType="Curve2D",
        Items=[
            ifc.createIfcPolyline([
                ifc.createIfcCartesianPoint([-half, 0.0]),
                ifc.createIfcCartesianPoint([half, 0.0]),
            ])
        ],
    )

    # Body repr: rectangle profile (length × thickness) extruded height in Z
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA",
        XDim=length,
        YDim=float(wall.thickness),
    )
    extrusion_pos = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=extrusion_pos,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(wall.height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )

    shape = ifc.createIfcProductDefinitionShape(
        Representations=[axis_repr, body_repr],
    )

    return ifc.createIfcWall(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name=f"Wall-{wall.id[:8]}",
        ObjectPlacement=placement,
        Representation=shape,
        PredefinedType="SOLIDWALL",
    )


# --------------------------------------------------------------------------- #
# Aukko-entiteetti (IfcOpeningElement + IfcRelVoidsElement)
# --------------------------------------------------------------------------- #

def _openings_by_wall(model: StructuralModel) -> dict[str, list[Opening]]:
    out: dict[str, list[Opening]] = {}
    for op in model.openings:
        out.setdefault(op.wall_id, []).append(op)
    return out


def _create_opening(
    ifc: ifcopenshell.file,
    wall_ent: ifcopenshell.entity_instance,
    wall: Wall,
    op: Opening,
    oh: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance:
    """Aukko seinän paikallisessa koordinaatistossa: leikkaa seinään reiän.
    Seinä on sijoitettu keskipisteeseen, X akselia pitkin → paikallinen
    x ∈ [-length/2, length/2], y koko paksuus, z ∈ [0, height]."""
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0)) or 1.0

    cx = op.position_along + op.width / 2.0 - length / 2.0   # aukon keskikohta seinäakselilla
    cut_thickness = float(wall.thickness) * 1.4              # ylileveä → varma läpileikkaus

    # Aukon placement seinän placementiin nähden (paikallinen X-siirto)
    rel = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([float(cx), 0.0, float(op.sill_height)]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    placement = ifc.createIfcLocalPlacement(
        PlacementRelTo=wall_ent.ObjectPlacement,
        RelativePlacement=rel,
    )

    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=float(op.width), YDim=cut_thickness,
    )
    extrusion_pos = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile, Position=extrusion_pos,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(op.opening_height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    label = {"door": "Ovi", "window": "Ikkuna"}.get(op.opening_type, "Aukko")
    opening_ent = ifc.createIfcOpeningElement(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name=f"{label}-{op.id}",
        ObjectPlacement=placement,
        Representation=shape,
        PredefinedType="OPENING",
    )
    ifc.createIfcRelVoidsElement(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        RelatingBuildingElement=wall_ent,
        RelatedOpeningElement=opening_ent,
    )

    # Täyte: oikea IfcDoor/IfcWindow ohuena paneelina aukossa (ei pelkkä reikä).
    is_window = op.opening_type == "window"
    panel_depth = min(float(wall.thickness), 60.0)
    fill_profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=float(op.width), YDim=panel_depth,
    )
    fill_solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=fill_profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(op.opening_height),
    )
    fill_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[fill_solid],
    )
    fill_shape = ifc.createIfcProductDefinitionShape(Representations=[fill_repr])
    fill_placement = ifc.createIfcLocalPlacement(
        PlacementRelTo=wall_ent.ObjectPlacement,
        RelativePlacement=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([float(cx), 0.0, float(op.sill_height)]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
    )
    if is_window:
        fill_ent = ifc.createIfcWindow(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"Ikkuna-{op.id}",
            ObjectPlacement=fill_placement, Representation=fill_shape,
            OverallHeight=float(op.opening_height), OverallWidth=float(op.width),
            PredefinedType="WINDOW",
        )
    else:
        fill_ent = ifc.createIfcDoor(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"Ovi-{op.id}",
            ObjectPlacement=fill_placement, Representation=fill_shape,
            OverallHeight=float(op.opening_height), OverallWidth=float(op.width),
            PredefinedType="DOOR",
        )
    ifc.createIfcRelFillsElement(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatingOpeningElement=opening_ent, RelatedBuildingElement=fill_ent,
    )
    return [opening_ent, fill_ent]


# --------------------------------------------------------------------------- #
# Laatta-entiteetti
# --------------------------------------------------------------------------- #

def _create_slab(
    ifc: ifcopenshell.file,
    slab: Slab,
    oh: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance | None:
    if len(slab.boundary) < 4:   # suljettu polygoni: vähintään 3 pistettä + sulkupiste
        return None

    # Placement: laatan yläpinnan z-tasolla
    base_z = slab.elevation - slab.thickness   # laatta kasvaa ylöspäin kohti elevation
    placement = _axis2placement(
        ifc,
        origin=[0.0, 0.0, float(base_z)],
        x_dir=[1.0, 0.0, 0.0],
    )

    # Boundary-polygoni paikallisessa XY-tasossa (placement offset huomioitu)
    pts_2d = [
        ifc.createIfcCartesianPoint([float(xy[0]), float(xy[1])])
        for xy in slab.boundary
    ]
    polyline = ifc.createIfcPolyline(pts_2d)
    profile = ifc.createIfcArbitraryClosedProfileDef(
        ProfileType="AREA",
        OuterCurve=polyline,
    )

    extrusion_pos = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=extrusion_pos,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(slab.thickness),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    ifc_type = {
        "floor": "FLOOR",
        "ceiling": "ROOF",
        "roof": "ROOF",
    }.get(slab.slab_type, "FLOOR")

    return ifc.createIfcSlab(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name=f"Slab-{slab.id[:8]}",
        ObjectPlacement=placement,
        Representation=shape,
        PredefinedType=ifc_type,
    )


# --------------------------------------------------------------------------- #
# Palkki-entiteetti (IfcBeam)
# --------------------------------------------------------------------------- #

def _create_beam(
    ifc: ifcopenshell.file,
    beam: Beam,
    oh: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance | None:
    p0 = np.array(beam.axis[0], dtype=float)
    p1 = np.array(beam.axis[1], dtype=float)
    vec = p1 - p0
    length = float(np.linalg.norm(vec))
    if length < 1.0:
        return None
    vec_n = vec / length

    mid = (p0 + p1) / 2.0
    half = length / 2.0

    # X-akseli palkin suuntaan, Z ylös
    x_dir = [float(vec_n[0]), float(vec_n[1]), float(vec_n[2])]
    placement = _axis2placement(
        ifc,
        origin=[float(mid[0]), float(mid[1]), float(mid[2])],
        x_dir=x_dir,
    )

    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA",
        XDim=length,
        YDim=float(beam.profile.width),
    )
    extrusion_pos = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, -float(beam.profile.height) / 2.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=extrusion_pos,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(beam.profile.height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    return ifc.createIfcBeam(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name=f"Beam-{beam.id[:8]}",
        ObjectPlacement=placement,
        Representation=shape,
        PredefinedType="BEAM",
    )


# --------------------------------------------------------------------------- #
# Pilari-entiteetti (IfcColumn)
# --------------------------------------------------------------------------- #

def _create_column(
    ifc: ifcopenshell.file,
    col: Column,
    oh: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance | None:
    if col.height < 100:
        return None

    placement = _axis2placement(
        ifc,
        origin=[float(col.location[0]), float(col.location[1]), float(col.base_z)],
        x_dir=[1.0, 0.0, 0.0],
    )

    if col.profile.shape == "circle":
        profile = ifc.createIfcCircleProfileDef(
            ProfileType="AREA",
            Radius=float(col.profile.width) / 2.0,
        )
    else:
        profile = ifc.createIfcRectangleProfileDef(
            ProfileType="AREA",
            XDim=float(col.profile.width),
            YDim=float(col.profile.depth),
        )

    extrusion_pos = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=extrusion_pos,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(col.height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    return ifc.createIfcColumn(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name=f"Column-{col.id[:8]}",
        ObjectPlacement=placement,
        Representation=shape,
        PredefinedType="COLUMN",
    )


# --------------------------------------------------------------------------- #
# Tila-entiteetti (IfcSpace)
# --------------------------------------------------------------------------- #

def _create_space(
    ifc: ifcopenshell.file,
    space: Space,
    oh: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
) -> ifcopenshell.entity_instance | None:
    if len(space.boundary) < 4:
        return None

    height = float(space.ceiling_z - space.floor_z)
    if height < 100:
        return None

    placement = _axis2placement(
        ifc,
        origin=[0.0, 0.0, float(space.floor_z)],
        x_dir=[1.0, 0.0, 0.0],
    )

    pts_2d = [
        ifc.createIfcCartesianPoint([float(xy[0]), float(xy[1])])
        for xy in space.boundary
    ]
    polyline = ifc.createIfcPolyline(pts_2d)
    profile = ifc.createIfcArbitraryClosedProfileDef(
        ProfileType="AREA",
        OuterCurve=polyline,
    )
    extrusion_pos = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=extrusion_pos,
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=height,
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    return ifc.createIfcSpace(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=oh,
        Name=f"Space-{space.id[:8]}",
        ObjectPlacement=placement,
        Representation=shape,
        PredefinedType="SPACE",
    )


def _axis2placement(
    ifc: ifcopenshell.file,
    origin: list[float],
    x_dir: list[float],
) -> ifcopenshell.entity_instance:
    ax3d = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint(origin),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection(x_dir),
    )
    return ifc.createIfcLocalPlacement(RelativePlacement=ax3d)

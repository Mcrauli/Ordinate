"""IFC4-kirjoitus: StructuralModel → .ifc

Hierarkia: IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey
Seinät:    IfcWall, axis-based + SweptSolid body (IfcRectangleProfileDef)
Yksiköt:   mm (IfcSIUnit MILLI METRE)
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import ifcopenshell
import ifcopenshell.guid

from scan2bim.schemas.model import StructuralModel, Wall


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

    wall_entities = [
        _create_wall(ifc, w, oh, body_ctx, axis_ctx)
        for w in model.walls
    ]

    if wall_entities:
        ifc.createIfcRelContainedInSpatialStructure(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=oh,
            RelatedElements=wall_entities,
            RelatingStructure=storey,
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

    # Placement: origin at midpoint, X along wall axis
    placement = _axis2placement(
        ifc,
        origin=[float(mid[0]), float(mid[1]), 0.0],
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

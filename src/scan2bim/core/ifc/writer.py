"""IFC4-kirjoitus: StructuralModel → .ifc

Hierarkia: IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey
Seinät:    IfcWall + IfcWallType + IfcMaterialLayerSet (muokattava arkkitehtityökaluissa)
Laatat:    IfcSlab (lattia) / IfcCovering CEILING (katto)
Aukot:     IfcOpeningElement + IfcDoor/IfcWindow + tyypit
Tilat:     IfcSpace + Qto-pinta-ala/korkeus

Jokaisella elementillä on:
  - TYYPPI (IfcRelDefinesByType) → ryhmittyy Revit/ArchiCAD-perheiksi/tyypeiksi
  - MATERIAALI (IfcRelAssociatesMaterial + layer set) → muokattava rakenne
  - PROPERTY SET (Pset_*Common: IsExternal, LoadBearing) → "mikä on mitä"
  - MÄÄRÄT (Qto_*BaseQuantities) → määräluettelot
Yksiköt: mm (IfcSIUnit MILLI METRE)
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
    body_ctx, axis_ctx = _contexts(ifc)
    caches = _new_caches()

    _write_model_elements(ifc, model, oh, storey, body_ctx, axis_ctx, caches)
    _emit_type_relations(ifc, oh, caches)
    ifc.write(str(path))


def write_building_ifc(models: list[StructuralModel], path: Path) -> None:
    """Yksi IFC, jossa kaikki kerrokset omina IfcBuildingStorey-tasoinaan."""
    models = [m for m in models if m is not None]
    if not models:
        return
    models = sorted(models, key=lambda m: (m.metadata.floor_index or 0))

    ifc = _build_project_skeleton()
    oh = ifc.by_type("IfcOwnerHistory")[0]
    building = ifc.by_type("IfcBuilding")[0]
    base_storey = ifc.by_type("IfcBuildingStorey")[0]
    body_ctx, axis_ctx = _contexts(ifc)
    caches = _new_caches()

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
        _write_model_elements(ifc, model, oh, storey, body_ctx, axis_ctx, caches)

    _emit_type_relations(ifc, oh, caches)
    ifc.write(str(path))


def _contexts(ifc):
    body_ctx = next(
        c for c in ifc.by_type("IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Body"
    )
    axis_ctx = next(
        c for c in ifc.by_type("IfcGeometricRepresentationSubContext")
        if c.ContextIdentifier == "Axis"
    )
    return body_ctx, axis_ctx


def _new_caches() -> dict:
    # materials: nimi→IfcMaterial; types: avain→type-entity; type_members: type→[instanssit]
    return {"materials": {}, "wall_types": {}, "slab_types": {}, "door_types": {},
            "window_types": {}, "covering_types": {}, "type_members": {}, "space_n": 0}


def _write_model_elements(ifc, model, oh, storey, body_ctx, axis_ctx, caches) -> None:
    elements = []
    openings_by_wall = _openings_by_wall(model)
    for w in model.walls:
        wall_ent = _create_wall(ifc, w, oh, body_ctx, axis_ctx, caches)
        elements.append(wall_ent)
        for op in openings_by_wall.get(w.id, []):
            elements.extend(_create_opening(ifc, wall_ent, w, op, oh, body_ctx, caches))

    for b in model.beams:
        e = _create_beam(ifc, b, oh, body_ctx)
        if e is not None:
            elements.append(e)
    for c in model.columns:
        e = _create_column(ifc, c, oh, body_ctx)
        if e is not None:
            elements.append(e)
    for s in model.slabs:
        e = _create_slab(ifc, s, oh, body_ctx, caches)
        if e is not None:
            elements.append(e)

    space_entities = []
    for sp in model.spaces:
        e = _create_space(ifc, sp, oh, body_ctx, caches)
        if e is not None:
            space_entities.append(e)

    if space_entities:
        ifc.createIfcRelContainedInSpatialStructure(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
            RelatedElements=space_entities, RelatingStructure=storey,
        )
    if elements:
        ifc.createIfcRelContainedInSpatialStructure(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
            RelatedElements=elements, RelatingStructure=storey,
        )


# --------------------------------------------------------------------------- #
# Semantiikka-apurit: property setit, määrät, materiaalit, tyypit
# --------------------------------------------------------------------------- #

def _val(ifc, v):
    if isinstance(v, bool):
        return ifc.createIfcBoolean(v)
    if isinstance(v, (int, float)):
        return ifc.createIfcReal(float(v))
    return ifc.createIfcLabel(str(v))


def _add_pset(ifc, element, oh, name: str, props: dict) -> None:
    properties = [
        ifc.createIfcPropertySingleValue(Name=k, NominalValue=_val(ifc, v))
        for k, v in props.items() if v is not None
    ]
    if not properties:
        return
    pset = ifc.createIfcPropertySet(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=name,
        HasProperties=properties,
    )
    ifc.createIfcRelDefinesByProperties(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatedObjects=[element], RelatingPropertyDefinition=pset,
    )


def _add_qto(ifc, element, oh, name: str, quantities: list) -> None:
    qs = []
    for kind, qn, val in quantities:
        if val is None:
            continue
        if kind == "length":
            qs.append(ifc.createIfcQuantityLength(Name=qn, LengthValue=float(val)))
        elif kind == "area":
            qs.append(ifc.createIfcQuantityArea(Name=qn, AreaValue=float(val)))
        elif kind == "volume":
            qs.append(ifc.createIfcQuantityVolume(Name=qn, VolumeValue=float(val)))
    if not qs:
        return
    eq = ifc.createIfcElementQuantity(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=name, Quantities=qs,
    )
    ifc.createIfcRelDefinesByProperties(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatedObjects=[element], RelatingPropertyDefinition=eq,
    )


def _material(ifc, caches, name: str):
    mats = caches["materials"]
    if name not in mats:
        mats[name] = ifc.createIfcMaterial(Name=name)
    return mats[name]


def _associate(ifc, oh, obj, relating_material) -> None:
    ifc.createIfcRelAssociatesMaterial(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatedObjects=[obj], RelatingMaterial=relating_material,
    )


def _register_type(caches, type_ent, instance) -> None:
    caches["type_members"].setdefault(type_ent, []).append(instance)


def _emit_type_relations(ifc, oh, caches) -> None:
    """Yksi IfcRelDefinesByType per tyyppi kaikille sen instansseille."""
    for type_ent, members in caches["type_members"].items():
        ifc.createIfcRelDefinesByType(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
            RelatedObjects=members, RelatingType=type_ent,
        )


def _wall_type(ifc, oh, caches, thickness: float, is_external: bool):
    key = (round(thickness), is_external)
    if key in caches["wall_types"]:
        return caches["wall_types"][key]
    if is_external:
        prefix, mat_name = "US", "Betoni"          # ulkoseinä
    elif thickness >= 180.0:
        prefix, mat_name = "KVS", "Betoni"          # kantava väliseinä
    else:
        prefix, mat_name = "VS", "Kipsilevyrunko"   # kevyt väliseinä
    label = f"{prefix} {round(thickness)} mm"
    mat = _material(ifc, caches, mat_name)
    layer = ifc.createIfcMaterialLayer(
        Material=mat, LayerThickness=float(thickness), IsVentilated=False, Name=mat_name,
    )
    mls = ifc.createIfcMaterialLayerSet(MaterialLayers=[layer], LayerSetName=label)
    wt = ifc.createIfcWallType(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=label,
        PredefinedType="SOLIDWALL",
    )
    _associate(ifc, oh, wt, mls)
    caches["wall_types"][key] = wt
    caches["_wall_mls"] = caches.get("_wall_mls", {})
    caches["_wall_mls"][wt] = mls
    return wt


# --------------------------------------------------------------------------- #
# Projekti-skeleton
# --------------------------------------------------------------------------- #

def _build_project_skeleton() -> ifcopenshell.file:
    ifc = ifcopenshell.file(schema="IFC4")
    oh = _make_owner_history(ifc)

    mm_unit = ifc.createIfcSIUnit(UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    area_unit = ifc.createIfcSIUnit(UnitType="AREAUNIT", Name="SQUARE_METRE")
    vol_unit = ifc.createIfcSIUnit(UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
    units = ifc.createIfcUnitAssignment(Units=[mm_unit, area_unit, vol_unit])

    wcs = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    ctx = ifc.createIfcGeometricRepresentationContext(
        ContextType="Model", CoordinateSpaceDimension=3, Precision=1e-5,
        WorldCoordinateSystem=wcs,
    )
    body_ctx = ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body", ContextType="Model", ParentContext=ctx,
        TargetView="MODEL_VIEW",
    )
    ifc.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Axis", ContextType="Model", ParentContext=ctx,
        TargetView="GRAPH_VIEW",
    )

    project = ifc.createIfcProject(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="scan2bim",
        UnitsInContext=units, RepresentationContexts=[ctx],
    )
    site = ifc.createIfcSite(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Site",
        CompositionType="ELEMENT",
    )
    building = ifc.createIfcBuilding(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Building",
        CompositionType="ELEMENT",
    )
    storey = ifc.createIfcBuildingStorey(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Kerros 1",
        CompositionType="ELEMENT", Elevation=0.0,
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


def _floor_elevation(model: StructuralModel) -> float:
    floor_slabs = [s.elevation for s in model.slabs if getattr(s, "slab_type", "") == "floor"]
    return float(min(floor_slabs)) if floor_slabs else 0.0


def _make_owner_history(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance:
    org = ifc.createIfcOrganization(Name="scan2bim")
    person = ifc.createIfcPerson(FamilyName="Rekola", GivenName="Lauri")
    p_and_o = ifc.createIfcPersonAndOrganization(ThePerson=person, TheOrganization=org)
    app = ifc.createIfcApplication(
        ApplicationDeveloper=org, Version="0.1.0",
        ApplicationFullName="scan2bim", ApplicationIdentifier="scan2bim",
    )
    return ifc.createIfcOwnerHistory(
        OwningUser=p_and_o, OwningApplication=app,
        ChangeAction="NOTDEFINED", CreationDate=int(time.time()),
    )


# --------------------------------------------------------------------------- #
# Seinä
# --------------------------------------------------------------------------- #

def _create_wall(ifc, wall, oh, body_ctx, axis_ctx, caches) -> ifcopenshell.entity_instance:
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
    is_external = getattr(wall.source, "method", "") == "floorplan"

    placement = _axis2placement(
        ifc, origin=[float(mid[0]), float(mid[1]), float(wall.z_min)],
        x_dir=[float(vec[0]), float(vec[1]), 0.0],
    )
    axis_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=axis_ctx, RepresentationIdentifier="Axis",
        RepresentationType="Curve2D",
        Items=[ifc.createIfcPolyline([
            ifc.createIfcCartesianPoint([-half, 0.0]),
            ifc.createIfcCartesianPoint([half, 0.0]),
        ])],
    )
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=length, YDim=float(wall.thickness),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(wall.height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[axis_repr, body_repr])

    wtype = _wall_type(ifc, oh, caches, wall.thickness, is_external)
    name = wtype.Name

    wall_ent = ifc.createIfcWall(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=name,
        Tag=wall.id, ObjectPlacement=placement, Representation=shape,
        PredefinedType="SOLIDWALL",
    )
    _register_type(caches, wtype, wall_ent)

    # Materiaalin kerrosrakenne instanssille (offset = -thickness/2 keskilinjasta)
    mls = caches.get("_wall_mls", {}).get(wtype)
    if mls is not None:
        usage = ifc.createIfcMaterialLayerSetUsage(
            ForLayerSet=mls, LayerSetDirection="AXIS2", DirectionSense="POSITIVE",
            OffsetFromReferenceLine=-float(wall.thickness) / 2.0,
        )
        _associate(ifc, oh, wall_ent, usage)

    _add_pset(ifc, wall_ent, oh, "Pset_WallCommon", {
        "Reference": name,
        "IsExternal": is_external,
        "LoadBearing": bool(is_external or wall.thickness >= 180.0),
        "ThermalTransmittance": None,
    })
    measured = getattr(wall, "measured_thickness", None)
    if measured is not None:
        _add_pset(ifc, wall_ent, oh, "scan2bim_Mittaus", {
            "MitattuPaksuus_mm": float(measured),
            "ToimitusPaksuus_mm": float(wall.thickness),
            "Poikkeama_mm": round(float(wall.thickness) - float(measured), 1),
        })
    vol = length * float(wall.thickness) * float(wall.height) / 1e9  # m³
    _add_qto(ifc, wall_ent, oh, "Qto_WallBaseQuantities", [
        ("length", "Length", length),
        ("length", "Height", float(wall.height)),
        ("length", "Width", float(wall.thickness)),
        ("volume", "GrossVolume", vol),
    ])
    return wall_ent


# --------------------------------------------------------------------------- #
# Aukko + ovi/ikkuna
# --------------------------------------------------------------------------- #

def _openings_by_wall(model: StructuralModel) -> dict[str, list[Opening]]:
    out: dict[str, list[Opening]] = {}
    for op in model.openings:
        out.setdefault(op.wall_id, []).append(op)
    return out


def _create_opening(ifc, wall_ent, wall, op, oh, body_ctx, caches) -> list:
    p0 = np.array(wall.axis[0], dtype=float)
    p1 = np.array(wall.axis[1], dtype=float)
    length = float(np.linalg.norm(p1 - p0)) or 1.0

    cx = op.position_along + op.width / 2.0 - length / 2.0
    cut_thickness = float(wall.thickness) * 1.4

    rel = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint([float(cx), 0.0, float(op.sill_height)]),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
    )
    placement = ifc.createIfcLocalPlacement(
        PlacementRelTo=wall_ent.ObjectPlacement, RelativePlacement=rel,
    )
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=float(op.width), YDim=cut_thickness,
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(op.opening_height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    label = {"door": "Ovi", "window": "Ikkuna"}.get(op.opening_type, "Aukko")
    opening_ent = ifc.createIfcOpeningElement(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"{label}-{op.id}",
        ObjectPlacement=placement, Representation=shape, PredefinedType="OPENING",
    )
    ifc.createIfcRelVoidsElement(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatingBuildingElement=wall_ent, RelatedOpeningElement=opening_ent,
    )

    is_window = op.opening_type == "window"
    panel_depth = min(float(wall.thickness), 60.0)
    fill_solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=ifc.createIfcRectangleProfileDef(
            ProfileType="AREA", XDim=float(op.width), YDim=panel_depth),
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
    wname = f"{round(op.width)}x{round(op.opening_height)}"
    if is_window:
        tkey = ("window", round(op.width), round(op.opening_height))
        wtype = caches["window_types"].get(tkey)
        if wtype is None:
            wtype = ifc.createIfcWindowType(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
                Name=f"Ikkuna {wname}", PredefinedType="WINDOW",
                PartitioningType="NOTDEFINED",
            )
            caches["window_types"][tkey] = wtype
        fill_ent = ifc.createIfcWindow(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"Ikkuna {wname}",
            Tag=op.id, ObjectPlacement=fill_placement, Representation=fill_shape,
            OverallHeight=float(op.opening_height), OverallWidth=float(op.width),
            PredefinedType="WINDOW",
        )
        _register_type(caches, wtype, fill_ent)
        _add_pset(ifc, fill_ent, oh, "Pset_WindowCommon", {
            "Reference": f"Ikkuna {wname}", "IsExternal": True,
        })
    else:
        tkey = ("door", round(op.width), round(op.opening_height))
        wtype = caches["door_types"].get(tkey)
        if wtype is None:
            wtype = ifc.createIfcDoorType(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
                Name=f"Ovi {wname}", PredefinedType="DOOR",
                OperationType="SINGLE_SWING_LEFT",
            )
            caches["door_types"][tkey] = wtype
        fill_ent = ifc.createIfcDoor(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"Ovi {wname}",
            Tag=op.id, ObjectPlacement=fill_placement, Representation=fill_shape,
            OverallHeight=float(op.opening_height), OverallWidth=float(op.width),
            PredefinedType="DOOR",
        )
        _register_type(caches, wtype, fill_ent)
        _add_pset(ifc, fill_ent, oh, "Pset_DoorCommon", {
            "Reference": f"Ovi {wname}", "IsExternal": False,
        })
    ifc.createIfcRelFillsElement(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        RelatingOpeningElement=opening_ent, RelatedBuildingElement=fill_ent,
    )
    return [opening_ent, fill_ent]


# --------------------------------------------------------------------------- #
# Laatta (lattia=IfcSlab, katto=IfcCovering CEILING)
# --------------------------------------------------------------------------- #

def _create_slab(ifc, slab, oh, body_ctx, caches) -> ifcopenshell.entity_instance | None:
    if len(slab.boundary) < 4:
        return None

    is_ceiling = getattr(slab, "slab_type", "floor") == "ceiling"
    base_z = slab.elevation if is_ceiling else slab.elevation - slab.thickness
    placement = _axis2placement(ifc, origin=[0.0, 0.0, float(base_z)], x_dir=[1.0, 0.0, 0.0])

    polyline = ifc.createIfcPolyline([
        ifc.createIfcCartesianPoint([float(xy[0]), float(xy[1])]) for xy in slab.boundary
    ])
    profile = ifc.createIfcArbitraryClosedProfileDef(ProfileType="AREA", OuterCurve=polyline)
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(slab.thickness),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])
    area = abs(_polygon_area(slab.boundary)) / 1e6  # m²

    if is_ceiling:
        ent = ifc.createIfcCovering(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Katto",
            Tag=slab.id, ObjectPlacement=placement, Representation=shape,
            PredefinedType="CEILING",
        )
        ctype = caches["covering_types"].get("ceiling")
        if ctype is None:
            ctype = ifc.createIfcCoveringType(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Kattopinta",
                PredefinedType="CEILING",
            )
            caches["covering_types"]["ceiling"] = ctype
        _register_type(caches, ctype, ent)
        _associate(ifc, oh, ent, _material(ifc, caches, "Kattolevy"))
        _add_pset(ifc, ent, oh, "Pset_CoveringCommon", {"IsExternal": False})
    else:
        ent = ifc.createIfcSlab(
            GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Lattia",
            Tag=slab.id, ObjectPlacement=placement, Representation=shape,
            PredefinedType="FLOOR",
        )
        stype = caches["slab_types"].get("floor")
        if stype is None:
            stype = ifc.createIfcSlabType(
                GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name="Lattialaatta",
                PredefinedType="FLOOR",
            )
            caches["slab_types"]["floor"] = stype
        _register_type(caches, stype, ent)
        _associate(ifc, oh, ent, _material(ifc, caches, "Betoni"))
        _add_pset(ifc, ent, oh, "Pset_SlabCommon", {
            "IsExternal": False, "LoadBearing": True,
        })
    _add_qto(ifc, ent, oh, "Qto_SlabBaseQuantities", [
        ("area", "GrossArea", area),
        ("length", "Width", float(slab.thickness)),
        ("volume", "GrossVolume", area * float(slab.thickness) / 1000.0),
    ])
    return ent


def _polygon_area(boundary) -> float:
    pts = np.array(boundary, dtype=float)
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# --------------------------------------------------------------------------- #
# Palkki / pilari
# --------------------------------------------------------------------------- #

def _create_beam(ifc, beam, oh, body_ctx) -> ifcopenshell.entity_instance | None:
    p0 = np.array(beam.axis[0], dtype=float)
    p1 = np.array(beam.axis[1], dtype=float)
    vec = p1 - p0
    length = float(np.linalg.norm(vec))
    if length < 1.0:
        return None
    vec_n = vec / length
    mid = (p0 + p1) / 2.0
    placement = _axis2placement(
        ifc, origin=[float(mid[0]), float(mid[1]), float(mid[2])],
        x_dir=[float(vec_n[0]), float(vec_n[1]), float(vec_n[2])],
    )
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=length, YDim=float(beam.profile.width),
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, -float(beam.profile.height) / 2.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(beam.profile.height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])
    return ifc.createIfcBeam(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"Palkki-{beam.id[:8]}",
        Tag=beam.id, ObjectPlacement=placement, Representation=shape,
        PredefinedType="BEAM",
    )


def _create_column(ifc, col, oh, body_ctx) -> ifcopenshell.entity_instance | None:
    if col.height < 100:
        return None
    placement = _axis2placement(
        ifc, origin=[float(col.location[0]), float(col.location[1]), float(col.base_z)],
        x_dir=[1.0, 0.0, 0.0],
    )
    if col.profile.shape == "circle":
        profile = ifc.createIfcCircleProfileDef(
            ProfileType="AREA", Radius=float(col.profile.width) / 2.0,
        )
    else:
        profile = ifc.createIfcRectangleProfileDef(
            ProfileType="AREA", XDim=float(col.profile.width), YDim=float(col.profile.depth),
        )
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=float(col.height),
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])
    return ifc.createIfcColumn(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh, Name=f"Pilari-{col.id[:8]}",
        Tag=col.id, ObjectPlacement=placement, Representation=shape,
        PredefinedType="COLUMN",
    )


# --------------------------------------------------------------------------- #
# Tila
# --------------------------------------------------------------------------- #

def _create_space(ifc, space, oh, body_ctx, caches) -> ifcopenshell.entity_instance | None:
    if len(space.boundary) < 4:
        return None
    height = float(space.ceiling_z - space.floor_z)
    if height < 100:
        return None

    placement = _axis2placement(ifc, origin=[0.0, 0.0, float(space.floor_z)], x_dir=[1.0, 0.0, 0.0])
    polyline = ifc.createIfcPolyline([
        ifc.createIfcCartesianPoint([float(xy[0]), float(xy[1])]) for xy in space.boundary
    ])
    profile = ifc.createIfcArbitraryClosedProfileDef(ProfileType="AREA", OuterCurve=polyline)
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=ifc.createIfcAxis2Placement3D(
            Location=ifc.createIfcCartesianPoint([0.0, 0.0, 0.0]),
            Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
            RefDirection=ifc.createIfcDirection([1.0, 0.0, 0.0]),
        ),
        ExtrudedDirection=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        Depth=height,
    )
    body_repr = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx, RepresentationIdentifier="Body",
        RepresentationType="SweptSolid", Items=[solid],
    )
    shape = ifc.createIfcProductDefinitionShape(Representations=[body_repr])

    caches["space_n"] += 1
    n = caches["space_n"]
    area = abs(_polygon_area(space.boundary)) / 1e6  # m²
    space_ent = ifc.createIfcSpace(
        GlobalId=ifcopenshell.guid.new(), OwnerHistory=oh,
        Name=f"{n:02d}", LongName="Tila",
        ObjectPlacement=placement, Representation=shape,
        CompositionType="ELEMENT", PredefinedType="INTERNAL",
    )
    _add_pset(ifc, space_ent, oh, "Pset_SpaceCommon", {
        "Reference": f"Tila {n:02d}", "IsExternal": False, "PubliclyAccessible": False,
    })
    _add_qto(ifc, space_ent, oh, "Qto_SpaceBaseQuantities", [
        ("area", "NetFloorArea", area),
        ("area", "GrossFloorArea", area),
        ("length", "Height", height),
        ("volume", "NetVolume", area * height / 1000.0),
    ])
    return space_ent


def _axis2placement(ifc, origin, x_dir) -> ifcopenshell.entity_instance:
    ax3d = ifc.createIfcAxis2Placement3D(
        Location=ifc.createIfcCartesianPoint(origin),
        Axis=ifc.createIfcDirection([0.0, 0.0, 1.0]),
        RefDirection=ifc.createIfcDirection(x_dir),
    )
    return ifc.createIfcLocalPlacement(RelativePlacement=ax3d)

"""Koordinaattijärjestelmät IFC-georeferointiin (IfcProjectedCRS + IfcMapConversion).

Geometria kirjoitetaan skannin OIKEISIIN maailmakoordinaatteihin (iso easting/
northing + korkeus) → overlay pistepilveä vasten (Cintoo tms.) osuu täsmälleen.
Georef-leima kertoo lisäksi MISSÄ järjestelmässä ne koordinaatit ovat, jotta
Revit/Navisworks osaa sijoittaa mallin shared/survey-koordinaateilla.

HUOM yksikkö: malligeometria on millimetreissä, projisoidut CRS:t metreissä →
IfcMapConversion.Scale = 0.001 (mm→m). Offset (Eastings/Northings/Height) = 0,
koska geometria kantaa jo täyden koordinaatin.
"""
from __future__ import annotations

# epsg → (label, projected-CRS Name, GeodeticDatum, VerticalDatum, MapProjection, MapZone)
# Suomen tyypilliset skannien järjestelmät + vanha KKJ.
CRS_PRESETS: dict[int, tuple[str, str, str, str, str, str]] = {
    3067: ("ETRS-TM35FIN (koko Suomi)", "EPSG:3067", "ETRS89", "N2000", "TM35FIN", "35"),
    3873: ("ETRS-GK19", "EPSG:3873", "ETRS89", "N2000", "ETRS-GKn", "19"),
    3874: ("ETRS-GK20", "EPSG:3874", "ETRS89", "N2000", "ETRS-GKn", "20"),
    3875: ("ETRS-GK21", "EPSG:3875", "ETRS89", "N2000", "ETRS-GKn", "21"),
    3876: ("ETRS-GK22", "EPSG:3876", "ETRS89", "N2000", "ETRS-GKn", "22"),
    3877: ("ETRS-GK23", "EPSG:3877", "ETRS89", "N2000", "ETRS-GKn", "23"),
    3878: ("ETRS-GK24", "EPSG:3878", "ETRS89", "N2000", "ETRS-GKn", "24"),
    3879: ("ETRS-GK25 (pääkaupunkiseutu)", "EPSG:3879", "ETRS89", "N2000", "ETRS-GKn", "25"),
    3880: ("ETRS-GK26", "EPSG:3880", "ETRS89", "N2000", "ETRS-GKn", "26"),
    3881: ("ETRS-GK27", "EPSG:3881", "ETRS89", "N2000", "ETRS-GKn", "27"),
    3882: ("ETRS-GK28", "EPSG:3882", "ETRS89", "N2000", "ETRS-GKn", "28"),
    3883: ("ETRS-GK29", "EPSG:3883", "ETRS89", "N2000", "ETRS-GKn", "29"),
    3884: ("ETRS-GK30", "EPSG:3884", "ETRS89", "N2000", "ETRS-GKn", "30"),
    3885: ("ETRS-GK31", "EPSG:3885", "ETRS89", "N2000", "ETRS-GKn", "31"),
    2393: ("KKJ / YKJ (vanha kansallinen)", "EPSG:2393", "KKJ", "N60", "Gauss-Kruger", "3"),
    3901: ("ETRS-TM35FIN + N2000 (3D)", "EPSG:3901", "ETRS89", "N2000", "TM35FIN", "35"),
}

DEFAULT_EPSG = 3067

# Geometria mm, projisoidut CRS metreissä → skaalaus mm→m.
MM_TO_M_SCALE = 0.001


def add_georef(ifc, context, epsg: int) -> None:
    """Lisää IfcProjectedCRS + IfcMapConversion. Geometria pysyy koskemattomana
    (oikeat koordinaatit); leima kertoo vain minkä CRS:n koordinaateista on kyse.

    epsg <= 0 → ei georef-leimaa (geometria silti oikeissa koordinaateissa)."""
    if not epsg or epsg <= 0:
        return
    preset = CRS_PRESETS.get(epsg)
    if preset is None:
        # tuntematon EPSG: kirjoita silti nimi, muut kentät auki
        name = f"EPSG:{epsg}"
        geodetic = vertical = projection = zone = None
    else:
        _label, name, geodetic, vertical, projection, zone = preset

    proj_crs = ifc.createIfcProjectedCRS(
        Name=name,
        GeodeticDatum=geodetic,
        VerticalDatum=vertical,
        MapProjection=projection,
        MapZone=zone,
    )
    ifc.createIfcMapConversion(
        SourceCRS=context,
        TargetCRS=proj_crs,
        Eastings=0.0,
        Northings=0.0,
        OrthogonalHeight=0.0,
        XAxisAbscissa=1.0,
        XAxisOrdinate=0.0,
        Scale=MM_TO_M_SCALE,
    )

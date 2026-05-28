# Arkkitehtuuri

## Tavoite

Pistepilvi (E57/LAS/PTS) → puhdas arkkitehtimalli. Tunnistaa rakenteet, suodattaa pois kalusteet ja LVI. Exportoi IFC + DXF + AutoLISP.

## Putki

```
[Point Cloud]  E57 / LAS/LAZ / PTS
      |
      ▼
[geometry]     Lataus, koordinaattinormalisointi, voxel-downsample (1-3 cm),
               kohinasuodatus (statistical outlier + radius filter)
      |
      ▼
[segmentation] ElementDetector-rajapinta — per elementtityyppi:
               WallDetector    → seinät  (RANSAC-tasodet. tai 2D-tiheys)
               SlabDetector    → lattia/katto
               ColumnDetector  → pilarit
               BeamDetector    → palkit
      |
      ▼
[semantics]    Centerline, paksuus, korkeus, tilojen johtaminen,
               confidence-pisteytys, krääsän suodatus
      |
      ▼
[StructuralModel JSON]  ← YDIN — kaikki export tästä
      |
      ├──▶ [ifc]     → model.ifc    (ifcopenshell, IfcWall/Slab/Column/Beam/Space)
      ├──▶ [export]  → model.dxf    (ezdxf)
      └──▶ [export]  → walls.lsp    (AutoLISP-skripti AutoCADille)
```

## Sisäinen schema (ydin)

Kaikki vaiheet lukevat ja kirjoittavat `StructuralModel`-objektin (`shared/schemas/`). Se on ainoa tiedonsiirtotapa vaiheiden välillä — ei globaaleja muuttujia, ei suoria riippuvuuksia vaiheiden välillä.

```
shared/schemas/model.py     StructuralModel, Wall, Slab, Column, Beam, Space
```

Jokainen elementti sisältää: `id`, `confidence`, `classification`, `source` (mistä menetelmästä tuli).

## ElementDetector-rajapinta

```python
class ElementDetector:
    def detect(self, cloud: o3d.geometry.PointCloud) -> list[Element]
```

Kaikki detektorit (Wall/Slab/Column/Beam) toteuttavat saman rajapinnan. Uusi elementtityyppi = uusi Detector-luokka, ei muutoksia muualle. Detektorit rekisteröidään `DetectorRegistry`-luokkaan.

## Tärkeät suunnittelupäätökset

| Päätös | Syy |
|--------|-----|
| Intermediate schema eikä suora point cloud → IFC | Kaikki exportit samasta lähteestä; debuggaus mahdollista |
| Deterministinen geometria ensin, ML myöhemmin | Helpompi debugata, ei kalibrointia, ennustettava |
| Walls-first kehitysjärjestys | Ohuin viipale joka todistaa koko putken |
| Seinädetektio: RANSAC vs 2D-tiheys bakeoff | Cloud2BIM käyttää tiheyttä (nopeampi), RANSAC intuitiivisempi; valinta datalla |
| ifcopenshell axis-based IfcWall | 1:1-kartoitus schemaan; ei raskasta mesh-generointia |
| Kaikki välidata tallennetaan data/intermediate/ | Debuggaus; jokainen vaihe ajettavissa erikseen |

## Riippuvuudet

```
open3d      — pistepilven käsittely, RANSAC
pye57       — E57-formaatin luku (Open3D ei natiivisti)
laspy       — LAS/LAZ-formaatin luku
numpy/scipy — numerinen käsittely
opencv      — 2D-morfologia (density-detektori)
ifcopenshell — IFC4-kirjoitus (LGPL; ok kaupallisessa käytössä pip-asennuksena)
ezdxf       — DXF-kirjoitus (MIT)
pydantic 2  — schema-validointi
```

## Referenssimateriaalit

- `reference/Cloud2BIM/` — validointiverrokki; sen tiheysalgoritmi on M4b:n inspiraatio
- `reference/dwg2ifc/` — IFC-kirjoituslogiikka (`src/dwg2ifc/`) ja AutoLISP-rutiinit (`autocad-tools/`) uudelleenkäytettävissä

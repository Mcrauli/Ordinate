# Arkkitehtuuri

> **Huom:** ajantasaisin putkikuvaus, moduulit ja opitut asiat ovat
> [`../AGENTS.md`](../AGENTS.md):ssä. Tämä tiedosto kuvaa periaatteet.

## Tavoite

Pistepilvi (E57/LAS/LAZ/PLY/PTS) → puhdas arkkitehtimalli. Tunnistaa rakenteet,
suodattaa pois kalusteet, exportoi älykkään IFC4:n + DXF.

## Putki

```
[Point Cloud]  E57 / LAS/LAZ / PLY / PTS  (yksi tai monta keilausta)
      |
      ▼
[geometry]     Lataus + metri→mm, voxel-downsample, kohinasuodatus,
               monikeilauksen hienorekisteröinti
      |
      ▼
[segmentation] contour-detektori (DEFAULT, Cloud2BIM-tyyli):
               monikerros-PYSTYMASKI (kalustesuodatus) → 2D-tiheysmaski →
               cv2.findContours → Douglas-Peucker → seinäakselit + paksuus.
               SlabDetector (lattia/katto), Opening/Column/Beam-detektorit.
      |
      ▼
[semantics]    pintalukitus, paksuus (raakapisteistä, sub-bin), ortogonalisointi,
               hienokierto, nurkkien sulku, perimetri, tilat, aukot
      |
      ▼
[StructuralModel JSON]  ← YDIN — kaikki export tästä
      |
      ├──▶ [ifc]     → building.ifc  (älykäs IFC4: IfcWallType/materiaalit/Pset/Qto)
      └──▶ [export]  → model.dxf      (ezdxf)
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

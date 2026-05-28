# scan2bim

Pistepilvi → puhdas arkkitehtimalli. Irrottaa rakenteet (seinät, laatat, pilarit, palkit) ja tilat point cloudista, suodattaa pois kalusteet ja LVI. Exportoi IFC + DXF + AutoLISP.

## Quickstart

```bash
# Asenna Python 3.12, sitten:
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Aja putki yhdellä komennolla:
python scripts/run_pipeline.py data/raw/your_scan.e57

# Tulos:
#   data/output/model.json   — sisäinen schema
#   data/output/model.ifc    — IFC-malli (avaa Solibrissa)
#   data/output/model.dxf    — DXF (AutoCAD)
#   data/output/walls.lsp    — AutoLISP-skripti
```

## Navigointi

| Haluat tietää...                    | Lue tämä                         |
|-------------------------------------|----------------------------------|
| Miten putki toimii kokonaisuutena   | `docs/ARCHITECTURE.md`           |
| Mikä moduuli tekee mitäkin          | `docs/module-map.md`             |
| Sisäinen datarakenne                | `shared/schemas/`                |
| Miten ajaa / kehittää               | `CLAUDE.md`                      |
| Testit                              | `tests/`                         |

## Arkkitehtuuri lyhyesti

```
Point Cloud (E57/LAS/PTS)
  ↓ backend/geometry    — lataus, normalisointi, downsample, kohinasuodatus
  ↓ backend/segmentation — ElementDetector: seinät, laatat, pilarit, palkit
  ↓ backend/semantics   — centerline, paksuus, korkeus, confidence, tilat
  ↓ shared/schemas      — StructuralModel JSON (ydin — kaikki export tästä)
  ↓ backend/ifc         — → IFC (ifcopenshell)
  ↓ backend/export      — → DXF (ezdxf) + AutoLISP
```

Yksityiskohdat: `docs/ARCHITECTURE.md`

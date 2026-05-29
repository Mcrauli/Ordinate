# scan2bim — CLAUDE.md

## Projektin idea

Pistepilvi → puhdas arkkitehtimalli (rakenteet + tilat, kalusteet/LVI pois). Kaupallinen tavoite.
Sovelluspohja kuten `dwg2ifc`: PySide6 GUI + CLI + PyInstaller .exe.

## Ympäristö

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,dev]"   # kaikki riippuvuudet + editable-asennus

pytest tests/                 # testit
scan2bim convert input.e57 output/   # CLI
python -m scan2bim            # GUI
```

Projektikansio: `C:/Users/LauriRekola/scan2bim`

Synteettinen testipilvi (jos ei oikeaa dataa):
```bash
python scripts/make_test_cloud.py --out data/raw/test_room.pts
scan2bim convert data/raw/test_room.pts data/output/test_room/
```

## Navigoi tästä

| Haluat tietää...                  | Lue tämä                              |
|-----------------------------------|---------------------------------------|
| Miten putki toimii                | `docs/ARCHITECTURE.md`                |
| Mikä moduuli tekee mitäkin        | `docs/module-map.md`                  |
| Testidatan hankinta + validointi  | `docs/testing.md`                     |
| Sisäinen datarakenne              | `src/scan2bim/schemas/model.py`       |
| GUI-rakenne                       | `src/scan2bim/gui/main_window.py`     |
| Pipeline-orkestroija              | `src/scan2bim/core/pipeline.py`       |

## Pääperiaatteet

1. **Schema on sopimus.** `src/scan2bim/schemas/model.py` — kaikki vaiheet schema sisään → schema ulos.
2. **ElementDetector-rajapinta.** Uusi elementtityyppi = uusi Detector-luokka (`core/segmentation/`), ei muutoksia muualle.
3. **Tallenna kaikki välidata.** `data/intermediate/` debuggausta varten.
4. **Deterministinen ensin, ML vasta myöhemmin.**
5. **Kolme kerrosta erillään** (kuten dwg2ifc): segmentointi (mikä se on) | geometria (miten mitataan) | export (miten kirjoitetaan).

## Uudelleenkäyttö

- IFC-kirjoituslogiikka: `reference/dwg2ifc/src/dwg2ifc/core/ifc_writer/` (skeleton + builders)
- AutoLISP-rutiinit: `reference/dwg2ifc/autocad-tools/`
- Validointiverrokki: `reference/Cloud2BIM/` (`python cloud2entities.py config.yaml`)

## Tech stack

Python 3.12, open3d, pye57, laspy, numpy, scipy, opencv-python, ifcopenshell (LGPL), ezdxf (MIT), pydantic 2, PySide6, click

## Rakenne (src/-layout)

```
src/scan2bim/
  schemas/     — StructuralModel (YDIN)
  core/
    geometry/  — lataus + esikäsittely
    segmentation/ — ElementDetector + detektorit
    semantics/ — centerline, paksuus, tilat, confidence
    ifc/       — IFC4-kirjoitus
    export/    — DXF + AutoLISP
    pipeline.py — orkestroija
  gui/         — PySide6-sovellus
  cli.py       — Click-CLI
```

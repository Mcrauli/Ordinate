# scan2bim — CLAUDE.md

## Projektin idea

Pistepilvi → puhdas arkkitehtimalli (rakenteet + tilat, kalusteet/LVI pois). Kaupallinen tavoite.

## Ympäristö

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest tests/
```

Projektikansio: `C:/Users/lauri/scan2bim`

## Navigoi tästä

- `docs/ARCHITECTURE.md` — koko putki + dataflow-kaavio
- `docs/module-map.md` — moduulikartta (vastuu + sisään/ulos per moduuli)
- `shared/schemas/` — sisäinen StructuralModel-schema (YDIN)
- `reference/` — Cloud2BIM + dwg2ifc (verrokki + uudelleenkäytettävä koodi)

## Pääperiaatteet

1. **Schema on sopimus.** Jokainen vaihe: schema sisään → schema ulos. Muuta schemaa vain `shared/schemas/`-kansiosta.
2. **ElementDetector-rajapinta.** Uusi elementtityyppi = uusi `Detector`-luokka, ei muutoksia muualle.
3. **Tallenna kaikki välidata.** `data/intermediate/` debuggausta varten.
4. **Deterministinen ensin, ML vasta myöhemmin.**
5. **Confidence joka elementille.** Matala confidence → flagataan tarkistukseen.

## Uudelleenkäyttö

- IFC-kirjoituslogiikka: `reference/dwg2ifc/src/dwg2ifc/` (ifcopenshell 0.8+)
- AutoLISP-rutiinit: `reference/dwg2ifc/autocad-tools/`
- Validointiverrokki: `reference/Cloud2BIM/` (`python cloud2entities.py config.yaml`)

## Tech stack

Python 3.12, open3d, pye57, laspy, numpy, scipy, opencv-python, ifcopenshell (LGPL), ezdxf (MIT), pydantic 2

## Testit

```bash
pytest tests/                    # kaikki
pytest tests/test_schema.py      # vain schema
pytest tests/ -k "geometry"      # filtteri
```

# scan2bim

[![Latest release](https://img.shields.io/github/v/release/Mcrauli/scan2bim-web?include_prereleases&sort=semver)](https://github.com/Mcrauli/scan2bim-web/releases/latest)

**Laserkeilauspilvi → puhdas arkkitehtoninen BIM-malli (IFC4).** scan2bim
lukee sisätilan pistepilven (E57 / LAS / LAZ / PLY / PTS), tunnistaa
rakenteet — **seinät, lattia, katto, ovet, ikkunat, pilarit, palkit ja
tilat** — suodattaa kalusteet ja krääsän pois, ja kirjoittaa **älykkään
IFC4-tiedoston**, jossa jokaisella elementillä on oikea tyyppi, materiaali,
property setit ja määrät → avautuu suoraan muokattavana Revitissä /
ArchiCADissa / Solibrissa.

Tavoite: tuottaa **inventointimallitason** pohja niin että arkkitehdin ei
tarvitse juuri korjailla mallia käsin.

Nykyinen versio: **v0.8.8** — pre-release-vaiheessa.

## Mitä se osaa

| Input | Tuotos |
|---|---|
| **Pistepilvi** (E57 / LAS / LAZ / PLY / PTS), yksi tai monta keilausta | **IFC4** + DXF |
| Kalustettu sisätila (asunto, toimisto, liiketila) | Rakenteet eroteltuna, kalusteet suodatettuna |
| Monta keilausta samasta kerroksesta | Yhdistetty malli (`run_floors`) |

**Älykäs IFC** — jokainen elementti tulee Revit/ArchiCAD-yhteensopivana:

- **Tyypit**: `IfcWallType` / `IfcDoorType` / `IfcWindowType` / `IfcSlabType` /
  `IfcCoveringType` + `IfcRelDefinesByType` → ryhmittyvät perheiksi/tyypeiksi
- **Materiaalit + kerrosrakenne**: `IfcMaterialLayerSet` → seinärakenne muokattavissa
- **Property setit**: `Pset_WallCommon` (IsExternal, LoadBearing), `Pset_SpaceCommon`, …
- **Määrät**: `Qto_WallBaseQuantities` (pituus, korkeus, paksuus, tilavuus), pinta-alat
- **Nimet**: VS / KVS / US + paksuus mm, tilat nimettyinä, katto `IfcCovering CEILING`
- **Georeferointi**: malli kirjoitetaan skannin **oikeisiin maailmakoordinaatteihin**
  (overlay pistepilveä vasten osuu täsmälleen, esim. Cintoo); `IfcProjectedCRS` +
  `IfcMapConversion` kertovat koordinaatiston Revitille (oletus ETRS-TM35FIN,
  valittavissa)

## Tarkkuus

Mitattu round-trip-validoinnilla (tunnettu malli → puhdas pilvi → pipeline → vertaa):

| Mitta | Puhdas data (algoritmin raja) | Kalustettu oikea skannaus |
|---|---|---|
| **Seinän paksuus** | **0.0 mm** (täydellinen) | mitattu ~0.7 mm; toimitukseen snäpätään rakennusstandardiin (66/92/120/200…) ja tarkka mitattu arvo tallennetaan IFC-propertyyn |
| **Kerroskorkeus** | <1 mm | ~4 mm (katto 0.3 mm) |
| **Nurkkasijainti** | ~4 mm | ~100 mm |

> **Miksi nurkkasijainti on heikompi oikealla datalla?** Kalustetussa
> tilassa suuri osa seinistä on **yksipuolisia** (vain sisäpinta keilattu;
> ulkopintaa ei nähdä) ja kalusteet peittävät nurkat (occluusio). Nämä ovat
> **datan fyysisiä rajoja, eivät algoritmin** — puhtaalla datalla sama
> pipeline antaa millimetritarkkuuden. Seuraava kehitysaskel (semanttinen
> suodatin, ks. [Roadmap](#roadmap)) puhdistaa kalusteet pois ja avaa tämän
> tarkkuuden myös oikealla datalla.

## Miten se toimii

Cloud2BIM-tyylinen **ääriviivapohjainen** seinädetektio + pistepilvestä
mitattu semantiikka:

```
E57 / LAS / LAZ / PLY / PTS  (yksi tai monta keilausta)
  → geometry/loader.py        lataus + metri→mm-automuunnos
  → geometry/preprocess.py    voxel-downsample + kohinasuodatus
  → segmentation/             contour-detektori: monikerros-pystymaski
                              (kalustesuodatus) → 2D-tiheysmaski → ääriviivat
                              → seinäakselit + paksuus
  → semantics/                pintalukitus + paksuusmittaus (raakapisteistä) +
                              ortogonalisointi + hienokierto + nurkkien sulku +
                              perimetri + huoneet + aukot
  → schemas/model.py          StructuralModel (JSON) — kaikki export tästä
  → ifc/writer.py             → IFC4 (tyypit, materiaalit, Pset, Qto, georef)
  → export/dxf.py             → DXF
```

Tarkka putki ja moduulit: [`AGENTS.md`](AGENTS.md) ja
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Lataa (Windows)

Uusin Windows-build on
[Releases-sivulla](https://github.com/Mcrauli/scan2bim-web/releases/latest):

- `scan2bim-Setup.exe` — Inno Setup -installeri (**per-user**, ei
  UAC-promptia, Start-menu + valinnainen desktop-shortcut)
- `scan2bim-X.Y.Z.exe` — paljas exe ilman asennusta
- `*.sha256` — checksumit (`Get-FileHash -Algorithm SHA256 tiedosto.exe`)

Sovellus **päivittää itsensä** GitHub Releasesista (per-user-asennus → ei
admin-oikeuksia). Windows SmartScreen voi varoittaa allekirjoittamattomasta
binääristä → **More info → Run anyway**.

## Käyttö

### GUI

```bash
python -m scan2bim          # tai asennettuna: scan2bim-gui
```

Valitse pistepilvi(t) → aja → tulokset (IFC / DXF / model.json).

### CLI

```bash
scan2bim convert input.e57 output/          # yksi keilaus
```

Tuotantopolku usealle keilaukselle on `Pipeline.run_floors([...])`
(yhdistää keilaukset yhdeksi kerrokseksi). Esimerkki:
[`data/_run_contour.py`](data/_run_contour.py).

Tulokset `output/`-kansiossa:
- `model.json` — sisäinen schema (StructuralModel)
- `building.ifc` — IFC4-malli
- `model.dxf` — DXF

## Kehitysympäristö

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,dev]"     # kaikki riippuvuudet + editable-asennus

pytest tests/                   # testit
python scripts/make_test_cloud.py --out data/raw/test_room.pts   # synteettinen testipilvi
```

Windows-build: `.\build.ps1` → `dist\scan2bim.exe`.
Installeri: `.\scripts\build_installer.ps1`.

## Tech stack

Python 3.12 · **open3d** (pistepilvet) · **opencv-python** (ääriviiva-rasteri) ·
**scipy / numpy** (sovitukset) · **ifcopenshell** (IFC4) · **ezdxf** (DXF) ·
**pydantic 2** (schema) · **PySide6** (GUI) · **click** (CLI) ·
**pye57 / laspy** (lataus). PyInstaller + Inno Setup (Windows-jakelu).

## Roadmap

- **Vaihe 2 — semanttinen suodatin (valmis, v0.8.0):** PointNet-ONNX-malli
  luokittelee pisteet (seinä/lattia/katto vs. kaluste/hylly/krääsä) ja suodattaa
  kalusteet, krääsän ja **liiketilojen lattia-katto-hyllyt** ennen geometrista
  putkea. CPU-inferenssi (ei GPU-pakkoa). Ks. [`AGENTS.md`](AGENTS.md).
- **Seuraavaksi:** nurkka-/kulmaviimeistely puhtaammalla pilvellä, lisää
  GT-validointia (SpatialLM-scenet), monikerros/monikorkuiset tilat.

## Dokumentaatio

| | Mihin |
|---|---|
| **Käyttäjälle** | Tämä README |
| **Kehittäjälle / AI-agentille** | [`AGENTS.md`](AGENTS.md) |
| **Arkkitehtuuri** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| **Moduulikartta** | [`docs/module-map.md`](docs/module-map.md) |
| **Testidata + validointi** | [`docs/testing.md`](docs/testing.md) |
| **Versiohistoria** | [`CHANGELOG.md`](CHANGELOG.md) |

## Lisenssi

Kaupallinen / yksityinen. Tekijä: **Lauri Rekola** (Mcrauli). IFC-kirjoitus
nojaa ifcopenshelliin (LGPL-3.0); kolmannen osapuolen lisenssit:
[`dist/LICENSES.md`](dist/LICENSES.md).

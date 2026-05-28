# Moduulikartta

Yksi rivi per tiedosto: **vastuu** + **sisään** → **ulos**. Lukemalla tämän tietää mistä mikäkin löytyy.

## src/scan2bim/schemas/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `model.py` | StructuralModel, Wall, Slab, Column, Beam, Space — kaikki pydantic-mallit | JSON ↔ Python-objekti |

## src/scan2bim/core/geometry/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `loader.py` | E57/LAS/PTS/PLY → Open3D PointCloud | tiedostopolku → `o3d.PointCloud` |
| `preprocess.py` | Normalisointi, voxel-downsample, kohinasuodatus | `o3d.PointCloud` → siivottu `o3d.PointCloud` |

## src/scan2bim/core/segmentation/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `base.py` | `ElementDetector`-rajapinta + `DetectorRegistry` | — |
| `wall_ransac.py` | Seinädetektio RANSAC-tasoilla (3D) | `o3d.PointCloud` → `list[Wall]` |
| `wall_density.py` | Seinädetektio 2D-tiheysanalyysi + morfologia | `o3d.PointCloud` → `list[Wall]` |
| `slab.py` | Lattia/katto-detektio (vaakatasot) | `o3d.PointCloud` → `list[Slab]` |
| `column.py` | Pilaridetektio (pystyklusterit) | `o3d.PointCloud` → `list[Column]` |
| `beam.py` | Palkkidetektio (vaaka-akselit katon alla) | `o3d.PointCloud` → `list[Beam]` |

## src/scan2bim/core/semantics/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `geometry.py` | Centerline, paksuus, korkeus elementeistä | raakakandidaatit → täydennetyt elementit |
| `spaces.py` | IfcSpace-tilojen johtaminen seinä/laattarajoista | `list[Wall]`, `list[Slab]` → `list[Space]` |
| `confidence.py` | Confidence-pisteytys kaikille elementeille | elementit → elementit + confidence |
| `clutter.py` | Krääsän (kalusteet/LVI) luokittelu ja suodatus | pisteet + rakenteet → `Discarded` |

## src/scan2bim/core/ifc/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `writer.py` | StructuralModel → IFC4-tiedosto (ifcopenshell) | `StructuralModel` → `.ifc` |
| `skeleton.py` | IfcProject → Site → Building → Storey (kuten dwg2ifc) | — |
| `builders.py` | per-elementti add_wall / add_slab / add_column / add_beam | `Element` → `IfcEntity` |

## src/scan2bim/core/export/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `dxf.py` | StructuralModel → DXF (ezdxf) | `StructuralModel` → `.dxf` |
| `autolisp.py` | StructuralModel → AutoLISP-skripti (.lsp) | `StructuralModel` → `.lsp` |

## src/scan2bim/core/pipeline.py

Orkestroija — ajaa kaikki vaiheet järjestyksessä. `Pipeline(config).run(input, output_dir)`.

## src/scan2bim/cli.py

CLI: `scan2bim convert input.e57 output/` — Click-pohjainen.

## src/scan2bim/gui/

| Tiedosto | Vastuu |
|----------|--------|
| `app.py` | `run()` — käynnistää QApplication + MainWindow |
| `main_window.py` | Pääikkuna (otsikko, splitter, statusbar, progressbar) |
| `file_panel.py` | Vasen paneeli: drag&drop, asetukset, Convert-painike |
| `log_panel.py` | Oikea paneeli: loki + tulosyhteenveto |
| `process_worker.py` | QThread — ajaa `Pipeline.run()` taustalla, emittoi signaaleja |
| `theme.py` | Sovelluksen QSS-tyyli + palette |

## tests/

```
tests/
  test_schema.py       — StructuralModel serialisointi/deserialisointi
  test_loader.py       — E57/LAS/PTS lataus (M2)
  test_preprocess.py   — downsample + kohinasuodatus (M2)
  test_wall_ransac.py  — RANSAC-seinädetektio synteettisellä pilvellä (M4a)
  test_wall_density.py — density-seinädetektio synteettisellä pilvellä (M4b)
  test_ifc_writer.py   — IFC-kirjoitus + validointi (M6)
  test_dxf_writer.py   — DXF-kirjoitus (M6)
```

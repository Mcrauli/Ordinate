# Moduulikartta

Yksi rivi per tiedosto: **vastuu** + **sisään → ulos**.

## src/scan2bim/schemas/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `model.py` | StructuralModel, Wall, Slab, Column, Beam, Space, Discarded — kaikki pydantic-mallit | JSON ↔ Python |

## src/scan2bim/core/geometry/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `loader.py` | E57/LAS/PTS/PLY → Open3D PointCloud; automaattinen m→mm-skaalaus | polku → `o3d.PointCloud` (mm) |
| `preprocess.py` | Normalisointi (min=0), voxel-downsample, statistical outlier removal | `o3d.PointCloud` → siivottu `o3d.PointCloud` |

## src/scan2bim/core/segmentation/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `base.py` | `ElementDetector` ABC-rajapinta | — |
| `wall_detector.py` | Seinädetektio iteratiivisella RANSAC-tasosegmentoinnilla | `o3d.PointCloud` → `list[Wall]` |
| `slab_detector.py` | Lattia/katto z-histogrammista + konveksi peite | `o3d.PointCloud` → `list[Slab]` |
| `column_detector.py` | Pilarit DBSCAN XY-projektiolla (kompaktit klusterit) | `o3d.PointCloud` → `list[Column]` |
| `beam_detector.py` | Palkit DBSCAN kattovyöhykkeessä (pitkänomaiset klusterit) | `o3d.PointCloud` → `list[Beam]` |

## src/scan2bim/core/semantics/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `spaces.py` | IfcSpace-tilojen johtaminen lattia/katto-laataista | `StructuralModel` → `list[Space]` |
| `clutter.py` | Krääsän (kalusteet/LVI) tunnistus ja Discarded-kirjaus | `o3d.PointCloud` + malli → `Discarded` |

## src/scan2bim/core/ifc/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `writer.py` | StructuralModel → IFC4 (IfcProject-hierarkia + kaikki elementtityypit) | `StructuralModel` → `.ifc` |

## src/scan2bim/core/export/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `dxf.py` | Seinät + laattarajat DXF-layereille (S-WALLS / S-FLOORS / S-ROOFS) | `StructuralModel` → `.dxf` |
| `autolisp.py` | LINE/PLINE-komennot AutoCADille | `StructuralModel` → `.lsp` |

## src/scan2bim/core/pipeline.py

Orkestroija — ajaa kaikki vaiheet järjestyksessä, tallentaa välidata `intermediate/`-kansioon.
`Pipeline(PipelineConfig).run(input_path, output_dir) → StructuralModel`

## src/scan2bim/cli.py

`scan2bim convert input.e57 output/` — Click-pohjainen CLI.

## src/scan2bim/gui/

| Tiedosto | Vastuu |
|----------|--------|
| `app.py` | `run()` — käynnistää QApplication + MainWindow |
| `main_window.py` | Pääikkuna: splitter-layout, progressbar, statusbar |
| `file_panel.py` | Drag&drop, tuloskansio, voxel-koko, export-valinnat, Convert-nappi |
| `log_panel.py` | Värillinen loki + tulosyhteenveto |
| `process_worker.py` | QThread — ajaa Pipeline.run() taustalla, emittoi progress/finished/failed |
| `theme.py` | Tumma QSS-tyyli + Fusion-palette |

## tests/

| Tiedosto | Testaa |
|----------|--------|
| `test_schema.py` | StructuralModel serialisointi, validointi, round-trip |
| `test_loader.py` | E57/LAS/PTS lataus, formaattivirhe |
| `test_preprocess.py` | Normalisointi, downsample, outlier removal |
| `test_wall_detector.py` | RANSAC-seinädetektio synteettisellä 4-seinäisellä huoneella |
| `test_slab_detector.py` | Z-histogram-laattadetektio lattia + katto |
| `test_column_detector.py` | DBSCAN-pilaridetektio 4 synteettisellä pilarilla |
| `test_beam_detector.py` | Palkkidetektio kattovyöhykkeestä |
| `test_spaces.py` | derive_spaces lattia/katto-kombinaatioilla |
| `test_clutter.py` | Kalusteklusterien tunnistus |

## scripts/

| Tiedosto | Käyttö |
|----------|--------|
| `make_test_cloud.py` | Generoi synteettinen PTS-testipilvi (`--out`, `--density`, `--seed`) |

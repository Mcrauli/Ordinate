# Moduulikartta

Yksi rivi per tiedosto: **vastuu** + **sisään** → **ulos**. Lukemalla tämän tietää mistä mikäkin löytyy.

## shared/schemas/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `model.py` | StructuralModel, Wall, Slab, Column, Beam, Space — kaikki pydantic-mallit | JSON ↔ Python-objekti |

## backend/geometry/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `loader.py` | E57/LAS/PTS/PLY → Open3D PointCloud | tiedostopolku → `o3d.PointCloud` |
| `preprocess.py` | Normalisointi, voxel-downsample, kohinasuodatus | `o3d.PointCloud` → siivottu `o3d.PointCloud` |

## backend/segmentation/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `base.py` | `ElementDetector`-rajapinta + `DetectorRegistry` | — |
| `wall_ransac.py` | Seinädetektio RANSAC-tasoilla (3D) | `o3d.PointCloud` → `list[Wall]` |
| `wall_density.py` | Seinädetektio 2D-tiheysanalyysi + morfologia | `o3d.PointCloud` → `list[Wall]` |
| `slab.py` | Lattia/katto-detektio (vaakatasot) | `o3d.PointCloud` → `list[Slab]` |
| `column.py` | Pilaridetektio (pystyklusterit) | `o3d.PointCloud` → `list[Column]` |
| `beam.py` | Palkkidetektio (vaaka-akselit katon alla) | `o3d.PointCloud` → `list[Beam]` |

## backend/semantics/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `geometry.py` | Centerline, paksuus, korkeus elementeistä | raakakandidaatit → täydennetyt elementit |
| `spaces.py` | IfcSpace-tilojen johtaminen seinä/laattarajoista | `list[Wall]`, `list[Slab]` → `list[Space]` |
| `confidence.py` | Confidence-pisteytys kaikille elementeille | elementit → elementit + confidence |
| `clutter.py` | Krääsän (kalusteet/LVI) luokittelu ja suodatus | `o3d.PointCloud` + rakenteet → `discarded` |

## backend/ifc/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `writer.py` | StructuralModel → IFC4-tiedosto (ifcopenshell) | `StructuralModel` → `.ifc` |
| `adapters.py` | Per-elementti IFC-kartoitukset (Wall→IfcWall jne.) | `Element` → `IfcEntity` |

## backend/export/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `dxf.py` | StructuralModel → DXF-tiedosto (ezdxf) | `StructuralModel` → `.dxf` |
| `autolisp.py` | StructuralModel → AutoLISP-skripti (.lsp) | `StructuralModel` → `.lsp` |

## backend/api/

| Tiedosto | Vastuu | Sisään → Ulos |
|----------|--------|---------------|
| `main.py` | FastAPI-sovellus (myöhemmin) | HTTP → pipeline → tiedostot |

## scripts/

| Tiedosto | Vastuu |
|----------|--------|
| `run_pipeline.py` | Koko putki yhdellä komennolla: lataa → detektoi → exportoi |

## tests/

```
tests/
  test_schema.py       — StructuralModel serialisointi/deserialisointi
  test_loader.py       — E57/LAS/PTS lataus
  test_preprocess.py   — downsample + kohinasuodatus
  test_wall_ransac.py  — RANSAC-seinädetektio (synteettisellä pilvellä)
  test_wall_density.py — density-seinädetektio (synteettisellä pilvellä)
  test_ifc_writer.py   — IFC-kirjoitus + validointi
  test_dxf_writer.py   — DXF-kirjoitus
```

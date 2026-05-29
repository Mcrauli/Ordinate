# scan2bim

Pistepilvi → puhdas arkkitehtimalli. Tunnistaa rakenteet (seinät, lattia/katto, pilarit, palkit, tilat) pistepilvestä ja suodattaa pois kalusteet ja LVI. Exportoi IFC4 + DXF + AutoLISP.

## Quickstart

```bash
# Asenna Python 3.12, sitten:
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,dev]"

# Synteettinen testipilvi (ei oikeaa dataa? luo tämä):
python scripts/make_test_cloud.py --out data/raw/test_room.pts

# CLI:
scan2bim convert data/raw/test_room.pts data/output/test_room/

# GUI:
python -m scan2bim

# Yksikkötestit:
pytest tests/
```

Tulokset kansiossa `data/output/test_room/`:
- `model.json` — sisäinen schema (StructuralModel)
- `model.ifc` — IFC4-malli (avaa Solibrissa / BIM Vision)
- `model.dxf` — DXF (AutoCAD)
- `walls.lsp` — AutoLISP-skripti

## Navigointi

| Haluat tietää...              | Lue tämä                    |
|-------------------------------|-----------------------------|
| Miten putki toimii            | `docs/ARCHITECTURE.md`      |
| Mikä moduuli tekee mitäkin    | `docs/module-map.md`        |
| Testidatan hankinta + validointi | `docs/testing.md`        |
| Sisäinen datarakenne          | `src/scan2bim/schemas/model.py` |
| Kehitysympäristö              | `CLAUDE.md`                 |

## Putki lyhyesti

```
E57 / LAS/LAZ / PTS
  -> geometry/loader.py     lataus + m->mm-automuunnos
  -> geometry/preprocess.py voxel-downsample + kohinasuodatus
  -> segmentation/          WallDetector | SlabDetector | ColumnDetector | BeamDetector
  -> semantics/             derive_spaces | detect_clutter
  -> schemas/model.py       StructuralModel JSON  (kaikki export tästä)
  -> ifc/writer.py          -> IFC4 (IfcWall, IfcSlab, IfcColumn, IfcBeam, IfcSpace)
  -> export/dxf.py          -> DXF
  -> export/autolisp.py     -> AutoLISP
```

## Build (.exe)

```powershell
.\build.ps1
# -> dist\scan2bim\scan2bim.exe
```

Vaatii: `pip install pyinstaller` (ajetaan automaattisesti build.ps1:ssä).

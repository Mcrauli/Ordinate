# Testaus ja validointi

## 1. Yksikkötestit

```bash
pytest tests/ -v
# 53 testiä — kaikki pitää mennä läpi ennen commitia
```

Testit kattavat: schema-sarjallistus, loader (E57/LAS/PTS), esikäsittely,
WallDetector, SlabDetector, ColumnDetector, BeamDetector, derive_spaces, clutter.

---

## 2. Synteettinen testipilvi (nopea smoke test)

Generoi realistinen 8×6×3 m sisätila (seinät, lattia, katto, 2 pilaria, 2 palkkia, kalusteita):

```bash
python scripts/make_test_cloud.py --out data/raw/test_room.pts

scan2bim convert data/raw/test_room.pts data/output/test_room/
```

Odotetut tulokset:

| Elementti | Odotettu | Huom |
|-----------|----------|------|
| Seinät | 4 | pituudet ~8000/6000 mm |
| Lattia + katto | 2 | z ≈ 0 ja 3000 mm |
| Pilarit | 2+ | kalusteita päätyy listalle (tunnettu rajoitus) |
| Palkit | 2-5 | DBSCAN voi jakaa pitkiä palkkeja |
| Tilat | 1 | |

Parametreja:

```bash
python scripts/make_test_cloud.py --density 80 --seed 123
# density = pisteitä/m² suurimmilla pinnoilla (oletus 50)
```

---

## 3. Julkinen testidataa

### Pienet testifileet (heti käytettävissä)

| Lähde | Formaatti | Koko | URL |
|-------|-----------|------|-----|
| libe57.org | E57 | ~MB | http://www.libe57.org/data.html |
| SourceForge E57Example | E57 | ~MB | https://sourceforge.net/projects/e57-3d-imgfmt/files/E57Example-data/ |
| Matterport Aon Lobby | E57 | ~100 MB | https://static.matterport.com/misc/UoqjwziqrZs-Aon_Lobby.e57 |

Matterport-tiedostossa on toimistolämminrakennus — hyvä ensimmäinen testi.
Lataa ja aja:

```bash
scan2bim convert Aon_Lobby.e57 data/output/aon_lobby/
```

### Isommat demo-aineistot

| Lähde | Formaatti | Koko | URL |
|-------|-----------|------|-----|
| Undet demo projects | E57 (FARO Focus X) | 852 MB | https://www.undet.com/undet-demo-projects/ |

### Benchmark-datasetti (ground truth IFC mukana)

**BIMNet** — paras validointiaineisto:
- 25 sisätilaskannausta + vastaavat IFC-mallit
- 116 M pistettä · 382 huonetta · 8 710 m²
- Open access (Tsinghua University 2025)
- https://thucbims.github.io/bimnet.thucbims.github.io/

BIMNetin avulla voi laskea kvantitatiivisia metriikoita (wall IoU, slab precision jne.) verraten omia tuloksia ground truth -IFC:hen.

---

## 4. Tulosten tarkastelu

### IFC-katselu

| Työkalu | Hinta | Huom |
|---------|-------|------|
| [Solibri](https://www.solibri.com/) | Kaupallinen | Paras laaduntarkistus |
| [BIM Vision](https://bimvision.eu/) | Ilmainen | Kevyt IFC-viewer |
| [FZK Viewer](https://www.iai.kit.edu/english/1648.php) | Ilmainen | KIT, tukee IFC4 |

### Pistepilvi vs. IFC — tarkkuusvertailu (CloudCompare)

[CloudCompare](https://www.cloudcompare.org/) on ilmainen työkalu pistepilven ja mallin vertailuun.

**Workflow:**

1. **Muunna IFC meshiksi** (ifcopenshell → OBJ):

```bash
python - <<'EOF'
import ifcopenshell, ifcopenshell.geom
import numpy as np

ifc = ifcopenshell.open("data/output/test_room/model.ifc")
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)

vertices, faces = [], []
offset = 0
for product in ifc.by_type("IfcProduct"):
    try:
        shape = ifcopenshell.geom.create_shape(settings, product)
        v = np.array(shape.geometry.verts).reshape(-1, 3)
        f = np.array(shape.geometry.faces).reshape(-1, 3) + offset
        vertices.append(v)
        faces.append(f)
        offset += len(v)
    except Exception:
        pass

if vertices:
    v_all = np.vstack(vertices)
    f_all = np.vstack(faces)
    with open("data/output/test_room/model.obj", "w") as out:
        for r in v_all:
            out.write(f"v {r[0]:.3f} {r[1]:.3f} {r[2]:.3f}\n")
        for r in f_all:
            out.write(f"f {r[0]+1} {r[1]+1} {r[2]+1}\n")
    print("model.obj kirjoitettu")
EOF
```

2. **Avaa CloudComparessa:**
   - File → Open: `data/raw/test_room.pts` (pistepilvi)
   - File → Open: `data/output/test_room/model.obj` (malli)

3. **Laske etäisyys:**
   - Valitse pistepilvi
   - Tools → Distances → Cloud/Mesh Dist
   - Aja → saat histogrammin ja RMS mm:nä

**Hyvä tulos:** RMS < 50 mm rakenteellisilla pinnoilla (seinät, lattia, katto).

---

## 5. Tunnetut rajoitukset

| Rajoitus | Syy | Korjaus (tuleva) |
|----------|-----|------------------|
| Pilarit löytävät kalusteita | Detektorit ajavat samasta pilvestä ilman inlier-vähennystä | Inlier-subtraktio detektorien välissä |
| Palkit jakautuvat segmenteiksi | DBSCAN harvan datan kanssa | Kollineaaristen segmenttien yhdistely |
| Tilat = lattian konveksi peite | Seinärajoja ei käytetä | Flood-fill 2D-ruudukkoon (v2) |
| Yksikkömuunnos heuristiikka | Kaikki < 500m → kerrotaan 1000:lla | Lue yksikkö E57-headerista |

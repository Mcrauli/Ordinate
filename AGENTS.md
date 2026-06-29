# scan2bim — kehittäjän ja AI-agentin opas

`scan2bim` on **laserkeilauspilvi → IFC4-arkkitehtimalli** -konvertteri:
lukee sisätilan pistepilven, tunnistaa rakenteet (seinät, lattia, katto, ovet,
ikkunat, pilarit, palkit, tilat), suodattaa kalusteet pois ja kirjoittaa
älykkään IFC4:n (tyypit + materiaalit + Pset + Qto). Tavoite: inventointimallitaso
jota arkkitehdin ei tarvitse juuri korjailla.

Tämä tiedosto on **kehittäjille ja AI-agenteille**: miten projekti toimii,
miten sitä kehitetään ja **mitä ei kannata keksiä uudelleen**. Loppukäyttäjän
kuvaus on [`README.md`](README.md):ssä.

## Pikastartti

Vaatimukset: **Python 3.12**.

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,dev]"      # riippuvuudet + editable
pytest tests/                    # testit (8 testitiedostoa)
python -m scan2bim               # GUI
```

Windows-build: `.\build.ps1` → `dist\scan2bim.exe` (~3–4 min).
Installeri: `.\scripts\build_installer.ps1` (vaatii Inno Setup 6).

**Tuotantopolku (oikea testaus):** `Pipeline.run_floors([pilvet], out)` — ei
yhden-tiedoston `convert`. Esimerkki [`data/_run_contour.py`](data/_run_contour.py)
(ajaa asuntodatan ~5 min). **Älä luota nopeaan 12mm-välimuistiin tarkkuuslukujen
mittaamiseen — se valehtelee; mittaa aina tuotantoajosta.**

## Golden rule (älä riko) — kolme kerrosta erillään

```
segmentation/   = mikä se on   (detektoi seinä/laatta/pilari pilvestä)
semantics/      = miten mitataan (paksuus, kulma, nurkat, tilat pistepilvestä)
ifc/ + export/  = miten kirjoitetaan (IfcWall, materiaalit, Pset, DXF)
```

- **Schema on sopimus.** `schemas/model.py::StructuralModel` — jokainen vaihe
  schema sisään → schema ulos. Kaikki export tulee tästä.
- **Uusi elementtityyppi = uusi Detector-luokka** (`segmentation/`,
  `DetectorRegistry.register`), ei muutoksia muualle.
- **Segmentointi ei mittaa, semantiikka ei detektoi, writer ei päättele tyyppiä uudelleen.**

## Pipeline (contour-detektori, default)

```
N x pistepilveä (run_floors yhdistää yhdeksi kerrokseksi)
  → geometry/loader.py          lataus + metri→mm-automuunnos
  → geometry/preprocess.py      voxel-downsample + kohinasuodatus
  → geometry/registration.py    (monikeilaus: hienorekisteröinti)
  → segmentation/wall_contour.py  DEFAULT-detektori:
        monikerros-PYSTYMASKI (kalustesuodatus) → 2D-tiheysmaski →
        cv2.findContours → Douglas-Peucker → seinäparit → akselit + paksuus
  → segmentation/slab_detector.py   lattia/katto z-piikeistä (sub-bin)
  → semantics/wall_semantics.py     filter_structural_walls, refine_thicknesses,
                                    _deduplicate, merge_collinear_walls
  → semantics/_recenter_wall_axes   pintalukitus (akseli skannatulle pinnalle)
  → semantics/perimeter.py          perimetriseinät lattiakontuurista
  → semantics/orthogonal.py         regularize_orthogonal + fine_rotate_walls
  → semantics/corner_snap.py        snap_corners, close_open_corners
  → pipeline._thickness_lock_walls  LOA-tarkka paksuus raakapisteistä (sub-bin)
  → TOIMITUSPAKSUUS                  snäppää standardiin [66,92,120,150,200,250,300]
                                    (mitattu arvo → Wall.measured_thickness)
  → semantics/room_detector.py      tilat (shapely polygonize)
  → segmentation/opening_detector.py  ovet/ikkunat
  → ifc/writer.py                   IFC4 (tyypit + materiaalit + Pset + Qto)
  → export/dxf.py                   DXF
```

`Pipeline.run_floors(paths, out)` on pää-entrypoint. Tarkka vaihejärjestys:
[`core/pipeline.py`](src/scan2bim/core/pipeline.py) `_detect`-metodi.

## Tärkeät tiedostot

| Tiedosto | Vastuu |
|---|---|
| `core/pipeline.py` | Orkestroija (`run_floors`, `_detect`, `_thickness_lock_walls`) |
| `core/segmentation/wall_contour.py` | **DEFAULT-detektori** + monikerros-pystymaski (kalustesuodatus) |
| `core/segmentation/slab_detector.py` | Lattia/katto z-piikeistä (sub-bin) |
| `core/segmentation/opening_detector.py` | Ovet/ikkunat |
| `core/segmentation/{column,beam}_detector.py` | Pilarit / palkit |
| `core/semantics/wall_semantics.py` | Suodatus, paksuus, dedup, `merge_collinear_walls` |
| `core/semantics/orthogonal.py` | `regularize_orthogonal` + `fine_rotate_walls` (kulma) |
| `core/semantics/corner_snap.py` | `snap_corners`, `close_open_corners` (nurkat) |
| `core/semantics/perimeter.py` | Perimetriseinät lattiakontuurista |
| `core/semantics/room_detector.py` | Tilat (shapely polygonize + sliver-suodatus) |
| `core/geometry/loader.py` | E57/LAS/LAZ/PLY/PTS-lataus + metri→mm |
| `core/ifc/writer.py` | **Älykäs IFC4**: tyypit, materiaalit, Pset, Qto |
| `core/export/dxf.py` | DXF-kirjoitus |
| `schemas/model.py` | `StructuralModel` (YDIN — kaikki export tästä) |
| `core/updater.py` + `gui/update_banner.py` | Itsepäivitys GitHub Releasesista |
| `cli.py` / `gui/app.py` | CLI / GUI entrypointit |
| `data/_*.py` | QA- ja vision-työkalut (ei pakattu exe:hen) |

## Mittarit ja validointi (`data/`)

Tarkkuus mitataan erillisillä QA-skripteillä — **aja tuotantomallia (`model.json`) vasten, ei välimuistia**:

| Skripti | Mittaa |
|---|---|
| `data/_synth_roundtrip.py` | **Round-trip**: tunnettu malli → puhdas pilvi → pipeline → paksuus/kulma/nurkka. Erottaa ALGORITMIN DATASTA. |
| `data/_element_qa.py` | Paksuus (HUOM: lukee SNÄPÄTTYÄ paksuutta, ei mitattua — ks. ansa alla) |
| `data/_corner_qa.py` | Nurkkasijainti vs pilvi-sovitetut keskilinjat |
| `data/_height_qa.py` | Lattia/katto/korkeus vs pilvi-sub-bin |
| `data/_length_qa.py` | Seinän pituus (nurkkaväli) |
| `data/_overlay_prod.py`, `data/_plan_qa.py`, `data/_vision_tol.py` | Vision-overlayt (malli vs pilvi) |

**Käytä visionia aina tarkkuusvertailuissa.** Kuvat: `data/_*.png`.

## Kovalla työllä opitut asiat — ÄLÄ keksi uudelleen

- **Kalustesuodatus = monikerros-pystymaski** (`wall_contour.py::_vertical_mask`):
  pikseli on seinää vain jos täynnä ≥55 % vaakaviipaleista (lattia→katto). Seinä
  ulottuu lattiasta kattoon; osakorkuinen kaluste putoaa. Yksi z-kaista EI riitä
  (kaluste samalla korkeudella läpäisee). **Liiketilojen lattia-katto-hyllyt EIVÄT
  suodatu tällä** — ne vaativat semanttisen suodattimen (Vaihe 2, roadmap).
- **Katto = ylin dominantti (tihein) z-piikki** = huoneesta näkyvä alapinta. ÄLÄ
  kävele alas lähipiikkeihin (tarttuu alakattoon → korkeus −170 mm). Korkeus =
  dominanttien lattia/katto-tasojen väli, EI z-ääripisteistä.
- **Paksuus mitataan raakapisteistä sub-bin-piikkisovituksella** (`_thickness_lock_walls`),
  ei voxel-välimuistista (12 mm voxel → ~33 mm virhe). Kaksipuoliset seinät → <1 mm.
  Yksipuolisia (ulkoseinät, vain sisäpinta keilattu) EI voi mitata — fyysinen raja.
- **Toimituspaksuus snäpätään standardiin** [66/92/120/150/200/250/300]; tarkka
  mitattu arvo → `Wall.measured_thickness` + IFC `scan2bim_Mittaus`-pset. Tämä on
  TUOTEPÄÄTÖS (arkkitehti haluaa muutaman siistin seinätyypin, ei 14 uniikkia).
- **METRIKKA-ANSA:** `_element_qa.py` lukee mallin SNÄPÄTTYÄ paksuutta → näyttää
  "isolta virheeltä" mutta on snap-by-design. **Todellinen mittaustarkkuus on
  `measured_thickness`-kentässä.** Älä tulkitse snäpättyä paksuutta accuracyna.
- **Nurkat: lopullinen `_deduplicate` ajettava AIVAN VIIMEISENÄ** (thickness_lock +
  snap jälkeen) — recenter/snap siirtää seinät päällekkäin vasta välidedupien
  jälkeen. Duplikaateista pidetään OHUEMPI (perimetri-swell paisuttaa 77→266 mm).
- **`merge_collinear_walls`** yhdistää saman seinän jaetut pätkät (eri paksuus →
  ohuempi); poisti 300 mm pöhö-artefaktit.
- **`close_open_corners`** sulkee vajaat nurkat TURVALLISESTI: vain avoimet päät,
  pareittain / tyhjä-venytys-ehdolla. **ISO `_resolve_corners`-extend (2400 mm)
  GRIDASI** (venytti sisäseinät ruudukoksi, 6→16 valehuonetta) — hylätty.
- **Nurkka-algoritmivirhe (~27 mm puhtaalla datalla) = jäännös-kulma.** Oikean
  rakennuksen seinät EIVÄT ole tarkalleen kohtisuoria (80–83°); `regularize_orthogonal`
  pakottaa ruudukkoon. **Iteroiva `fine_rotate` korjaa sen synteettisellä (27→4 mm,
  paksuus 0 mm), MUTTA yli-kiertää kalustetulla** (kaluste = valepinta kaistalla).
  → Nurkkatarkkuus on KYTKETTY Vaihe 2:n (kalustesuodatus) kanssa.
- **`fine_rotate` on herkkä — kytkeytyy paksuuteen.** Yhden pinnan sovitus kiertää
  akselin sen pinnan mukaan → toinen pinta vinoon → thickness_lock mittaa väärin.
  Sovita AINA molemmat pinnat (keskilinja). Älä nosta `_FINE_MAX_DEG`-cappia ilman
  reaalidatan thickness-validointia.
- **Standardipaksuus-snäppäys MITATUILLE seinille hylätty kerran** (2.6→6.0 mm):
  todelliset paksuudet eivät ole oletettuja vakioita. Snäppäys vain TOIMITUS-
  vaiheessa, mitattu arvo aina talteen.

## Tunnetut rajoitukset

- **Pipeline on viritetty yksikerroksiselle tilalle** (yksi lattia + yksi katto).
  Monikorkuinen tila (esim. 3DSES-koulu, 7 m porras) rikkoo globaalin korkeuden →
  seinät väärään korkeuteen. Per-huone-korkeus on roadmapilla.
- **Yksipuolisten (ulko)seinien paksuutta/sijaintia ei voi mitata** — vain sisäpinta
  keilattu. Fyysinen raja, ei bugi.
- **Occluusio** (kalusteet nurkissa) rajaa nurkkasijainnin ~100 mm:iin kalustetulla
  datalla. Puhtaalla rungolla sama pipeline antaa ~mm.
- **Liiketilojen hyllyt** (lattia-katto) läpäisevät geometrisen pystymaskin →
  Vaihe 2 (semanttinen suodatin) tarvitaan.

## Roadmap — Vaihe 2: semanttinen suodatin

Tavoite: suodattaa **kaikki kalusteet ja krääsä** (myös liiketilojen hyllyt) pois
ennen geometrista putkea → puhdas rakenteellinen pilvi. Tämä:
1. ratkaisee hyllyt/kalusteet robustisti (geometria ei riitä), ja
2. avaa nurkkatarkkuuden (iteroiva fine_rotate toimii puhtaalla pilvellä).

Lähestyminen: pistepilven **per-piste-semanttinen segmentointi** (seinä/lattia/
katto/pilari/ovi/ikkuna vs. pöytä/tuoli/hylly/clutter). Avoin pretrained-malli
(S3DIS-luokat sis. `bookcase`/`clutter`). Reunaehto: sovellus = PyInstaller-exe
**ilman GPU:ta** → keventettävä (ONNX/CPU) tai ajettava harvennetulle pilvelle.
Uusi `SemanticFilter`-esivaihe: pilvi → suodatettu pilvi → nykyinen pipeline
(minimaalinen muutos). Validointi: 3DSES (per-piste-labelit + CAD).

**Testidata:** `data/_3dses/` (Zenodo 13323342, TLS npy Nx7 + CAD .obj),
`Downloads/aligned_low_{apartment,bedroom}`, `gargage.e57`. Rohbau3D (GitHub,
kalustamaton runko) = paras puhdas tarkkuustesti, ei vielä ladattu.

## Työskentelyn konventiot

- **Suomi** chatissa ja dokumenteissa, **englanti** commit-viesteissä ja koodikommenteissa.
- **Suora push masteriin** sallittu (henkilökohtainen repo, ei PR-flowta).
- Commit-trailer AI-commiteissa: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Versiopumppi** koskettaa: `src/scan2bim/_version.py`, `build/version_info.py`
  (4 kenttää). `v*.*.*`-release julkaistaan **`Mcrauli/scan2bim-web`**-repoon
  (raaka exe + sha256 + Setup.exe) → itsepäivitys hakee sen.
- **Koodi: ei kommentteja ellei pyydetä; ei ennenaikaisia abstraktioita.**
- **Tarkkuusväitteet aina mitattuna** (QA-skripti + vision), ei arviona.

## Hakemistorakenne

```
src/scan2bim/
  schemas/      StructuralModel (YDIN)
  core/
    geometry/   lataus + esikäsittely + rekisteröinti
    segmentation/ detektorit (wall_contour = default)
    semantics/  paksuus, kulma, nurkat, tilat
    ifc/        IFC4-kirjoitus (writer.py)
    export/     DXF
    pipeline.py orkestroija (run_floors)
  gui/          PySide6-sovellus
  cli.py        Click-CLI
data/           QA- ja vision-työkalut (_*.py) + testidata (gitignore: *.ply/*.npy/*.png)
docs/           ARCHITECTURE.md, module-map.md, testing.md
build/          PyInstaller-spec + Inno Setup + version_info
scripts/        build/release-skriptit
reference/      dwg2ifc (arkkitehtuurimalli) + Cloud2BIM (verrokki)
```

## Dokumentaation ylläpito

Kun muutat koodia, päivitä `README.md` / `AGENTS.md` / `CHANGELOG.md` /
`docs/*.md` samassa commitissa jos muutos vaikuttaa käyttäjän workflow:hon,
pipelineen, IFC-outputtiin, tarkkuuteen tai releaseen. **Definition of Done:**
testit läpi *ja* dokumentit vastaavat koodin nykytilaa.

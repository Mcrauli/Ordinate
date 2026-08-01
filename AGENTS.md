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
  → ifc/writer.py                   IFC4 (tyypit + materiaalit + Pset + Qto +
                                    georef-leima ifc/crs.py; geometria skannin
                                    oikeissa maailmakoordinaateissa)
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
| `core/ifc/crs.py` | Georef-leima (`IfcProjectedCRS`+`IfcMapConversion`), `CRS_PRESETS` (EPSG) |
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
| `data/_extent_qa.py` | **Ylivenytys**: onko seinän PÄÄ katteessa vai ilmassa (kattamaton keskiosa = oviaukko, laillinen; kattamaton häntä = venytetty evidenssin yli) |
| `data/_val4.py`, `data/_ablation.py` | 4 datan tuotantoajo / ablaatio (monkeypatchaa muutos pois → näyttää ansaitseeko se paikkansa) |
| `data/_overlay_prod.py`, `data/_plan_qa.py`, `data/_vision_tol.py`, `data/_cmp_view.py` | Vision-overlayt (malli vs pilvi) |
| `data/_spatiallm_qa.py` | **Ground-truth-vertailu**: SpatialLM-scenet (PLY + .txt-annotaatio) → seinien lateraali-/kulmavirhe + aukkomäärät GT:tä vasten |
| `data/_synth_retail.py` | **Liiketila + mittakaava**: generoi parametrisen big-box-myymälän (pilarikenttä, palkisto, lasijulkisivu, taustatilat, gondolit JA lattia-katto-hyllyköt) tunnetulla pohjalla → `.gt.json`. Oma data ⇒ lisenssivapaa myös markkinointiin |
| `data/_retail_qa.py` | Malli vs. em. GT: kattavuus, lateraali-/paksuusvirhe, **montako seinää syntyi hyllykön etupinnalle** |
| `data/_scale_run.py` | Tuotantoajo jossa **aika ja huippumuisti vaiheittain** (`psutil`-näytteistys + progress-merkit) |
| `data/_room_probe.py`, `data/_frag_probe.py`, `data/_tl_probe.py` | Miksi tila hylättiin / onko perimetri pirstoutunut / miten paksuus syntyi |

**Käytä visionia aina tarkkuusvertailuissa.** Kuvat: `data/_*.png`.

**VALIDOI MITTARI KONTROLLIAJOLLA.** Uusi mittari on ajettava myös VANHAA
(huonompaa) mallia vasten. Jos se antaa molemmille samat luvut, se ei erottele
eikä sillä saa perustella mitään. Näin kävi `_angle_qa.py`:lle: se luki mitä
tahansa pisteitä ±45 mm kaistastaan (myös naapuriseinän ja kalusteen pintaa) →
PCA antoi väärän pinnan suunnan, ja se näytti vanhan mallin yhtä hyvänä.
Sijaintitarkkuus mitataan `_tol_heatmap.py`:n `pinta.mit`-sarakkeella
raakapilveä vasten. **Älä myöskään päättele tarkkuutta overlay-kuvasta** —
"wall_007 kierossa 1–2°, 350 mm pään virhe" oli kuvasta luettu eikä mittaus
tukenut sitä kummassakaan mallissa.

**Mitattu tarkkuus v0.8.9** (asunto, 48 M pistettä satunnaisotannalla 7
keilauksesta — EI voxelointia, joka siirtäisi pintaa): jokainen detektoitu
seinä ≤ 5.1 mm pinnastaan (v0.8.8: kolme yli 8 mm, pahin 34.2 mm), mediaani
3.8 mm. Jäännös on perimetriseinä sotkunurkassa (58.8 mm) jossa kaistan kohina
on 30.6 mm — se lippuuntuu itse conf 0.25 → QA:n TARKISTA-lista.
**Mitattu tarkkuus liiketilassa** (synteettinen 72×48×7 m myymälä, 8.2 M pistettä,
GT tunnettu): kaikki 9 GT-seinää löytyi, **jokainen 24 seinästä ≤0.4 mm** pinnastaan
(`_tol_heatmap`, `pinta.snap`). Ennen korjausta kaksi ulkoseinää 57.4 ja 62.1 mm.
Avoimet puutteet: ks. "Tunnetut rajoitukset → LIIKETILA".
**GT-testidata:** SpatialLM-Dataset (HuggingFace manycore-research) — yksittäiset
scenet saa ulos 4.8GB-chunkeista `remotezip`illä (range-request, ei koko latausta);
layout-chunkit (1.85MB) sisältävät Wall/Door/Window-annotaatiot samoille sceneille.

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
  jälkeen. Duplikaateista pidetään PISIN jänne (lyhyt korkean confidencen
  fragmentti EI saa syrjäyttää koko seinää: 2.2 m pätkä söi 6.8 m perimetrin,
  1.1 m pysty söi 3.4 m aidosti vinon — kadonnut jänne ei korjaannu, lateraali
  korjataan pintalukituksessa). Yhtä pitkistä korkein confidence, sitten OHUEMPI
  (perimetri-swell paisuttaa 77→266 mm).
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
- **Katto/lattia ovat histogrammin REUNAbinejä** — `find_peaks` ei tunnista reunaa
  piikiksi ilman nollapehmustusta → katoksi valikoitui alempi rakenne (−500 mm).
  Parikävely (450 mm) vain VERTAILUKELPOISEEN piikkiin (≥0.7×): laattaparin pinnat
  ovat ~yhtä vahvoja, alakatto/kotelo/kaapinpäällys on selvästi heikompi.
- **Lattiakontuurin lovi voi olla kalusteen keilausvarjo** (sänky/sohva): siitä
  tehty perimetriseinä risteilee huoneen halki. Testi: jos katto jatkuu reunan
  ULKOpuolella, reuna on sisätilassa → ei seinää (`perimeter._ceiling_continues_beyond`).
- **HUONEALA ≠ ohut lattiaviipale.** Kalusteiden keilausvarjot syövät ±8 mm
  viipaleeseen lahdet ulkoreunaan asti, cv2:n ulkokontuuri kiertää joka lahden ja
  **suhteellinen** `approxPolyDP`-epsilon (`0.008 × arcLength`) räjähtää lahtien
  myötä ~800 mm:iin → lahdet romahtavat **itsensä leikkaavaksi** monikulmioksi
  (mitattu asunnolla: 25 kärkeä, 36.9 m² kun ala on 58 m², `is_valid=False`).
  Silloin signed area — eli perimetrin ULOSPÄIN-normaali — on merkityksetön ja
  seiniä syntyy fiktiivisille diagonaalireunoille (haamu 600 mm rakennuksen ulkona,
  **0 pistettä** koko 3.4 m matkalla). Resepti (`_occupancy_grid`): lattia ∪ katto,
  ±40 mm kaista, 400 mm closing, reikien flood-fill, **absoluuttinen** epsilon
  150 mm, `_repair_polygon` (buffer(0) tai pudota). → 31 kärkeä, 57.7 m², validi.
- **Huoneala ei saa ylittää seinää** (`_cut_walls`): detektoidut seinät rasteroidaan
  maskiin katkaisijoiksi (min 120 mm leveys — 66 mm seinä ei katkaise 25 mm
  ruudukossa). Ilman tätä ala vuotaa oviaukoista ja lasin läpi naapuritilaan
  (mitattu: 114 639 kattopistettä yläseinän takana) → perimetri asettuu
  yhdistyneen alueen ULKOreunaan ja aito seinä kuolee snap-kaskadissa.
  Siksi kontuuri lasketaan VASTA seinien suodatuksen jälkeen.
- **Katto vain SULKEE varjot, se ei saa LUODA aluetta**: alueen pinta-alasta oltava
  ≥20 % lattiapisteiden peitossa (`_FOOT_MIN_FLOOR_FRAC`). Mitattu: keilausvuoto
  lasin/oviaukon läpi 0.02, aidot huoneet 0.60–0.97.
- **Mitattu linja voittaa kontuuri-priorin** (`perimeter._adopt_measured_line`):
  jos samalla linjalla on detektoitu seinä (≤700 mm, <8°, ≥1000 mm) mutta eri
  kohdassa pitkittäin — jolloin `_edge_covered`:n 0.35-peitto ei laukea —
  perimetri projisoidaan SEN keskilinjalle ja perii sen paksuuden, eikä
  `push`-korjausta käytetä. Kontuurin sijaintivirhe voi olla satoja mm eikä
  floorplan-seinän 90 mm linjauskorjaus riitä.
- **Paksuuspari hylätään jos seinän RUNGOSSA on kattoa** (`_pair_body_has_ceiling`,
  vain ≥210 mm pareille — ohuemman rungosta ei voi mitata). Yksipuolisella
  ulkoseinällä huoneen puolella oleva kaluste ~300 mm pinnasta tuottaa toisen
  piikin → paksuus 330–372 mm ja akseli **puoli valepaksuutta huoneen sisään** →
  naapuripätkä jää eri linjalle, `merge_collinear` (130 mm) ei sulauta → huone ei
  sulkeudu (apt2: 33 m² huone katosi). Katossa ei ole kalusteita, joten kattoa
  rungon sisällä = runko on osittain huonetilaa (mitattu: valepari 0.93–0.97,
  aidot ≤0.52). **Hylkäys palauttaa yksipuoliseksi MYÖS paksuudelta** (200 mm) —
  pelkkä paksuuden säilytys jättäisi akselin edelleen pieleen. Kattopisteet on
  annettava erikseen: `thick_cloud` on vain keskikaista (35–65 % z:stä), siinä ei
  ole kattoa lainkaan.
- **Valeseinät toimivat snap-ankkureina** — kaskadi: valeseinä → `snap_corners`
  venyttää naapurit sen risteyksiin → oikea seinä jää orvoksi → `remove_dangling_walls`
  poisti sen (3.4 m seinä, 34 k pisteen evidenssi!). Siksi dangling-poisto koskee
  vain <2.5 m tynkiä. Juurisyy on AINA valeseinä, ei snap.
- **Aidosti vino seinä (3–8°)**: `refine_skew_walls` (toinen passi täysipitkällä
  akselilla) palauttaa kulman PCA + pintaverifioinnilla (ohut pinta + kate).
  Ensimmäinen fine_rotate ei voi — vino detektiopätkä on usein <1.5 m ennen snappia
  ja leveä kaista poimii verhot/karmit (PCA laimenee; viimeistely kapealla kaistalla).
- **SpatialLM-GT:n viivat ovat seinäpintoja** — ~100 mm (puolikas paksuus) ero
  akseliin on konventio, ei virhe. Synteettisissä sceneissä kiintokomerot ovat
  täyskorkeita → näkyvät "seininä" (PointNet ei erota) — käytävän eteläseinä voi
  detektoitua komeron etupintaan (~500 mm sisään). Tunnettu jäännösvirhe.
- **Pistetason QA-luku ≠ mallin tarkkuus.** Pilven oma kohina (synteettinen
  SpatialLM ~15–20 mm RMS, oikea TLS 2–6 mm) dominoi pistetason mediaania.
  Mallin tarkkuus = pintamediaani vs mallipinta (QA:n Pintatarkkuus-osio,
  `data/_tol_heatmap.py`). Seinäpinnat mitatusti 0.0–0.2 mm GT-asunnolla.
- **Pintalukituksen jälkeen EI saa ajaa tavallista snap_cornersia** — T-liitos-
  projektio vetää päätepisteen naapurilinjalle ja kallistaa seinää ~5 mm.
  Käytä `snap_corners(walls, preserve_lines=True)` (päät liikkuvat vain oman
  akselin suunnassa linja-linja-leikkauksiin). Samasta syystä toimituspaksuus-
  snäppäys ajetaan ENNEN lopullista pintalinjausta (ja ankkuroituna).
- **Huippu ≠ mediaani kallellaan olevalla seinällä**: histogrammipiikki ja koko
  korkeuden pintamediaani eroavat 3–6 mm (lean/vino kohina). Pystyprisman paras
  sovitus on mediaani — lopullinen linjaus käyttää sitä (sama kuin QA-mittari).
- **Kaikille seinille yhteinen kulmaviimeistely kokeiltu ja HYLÄTTY** (pinta
  2.1→14.6 mm): ohut-pinta-verifiointi läpäisee myös VÄÄRÄT pinnat (verho/
  komero on ohut taso). Skew-polku vain aidosti vinoille (≥3°).
- **Korkeasokkeliset ikkunat (sokkeli >~600 mm) eivät löydy** sarakedetektiolla
  (lattiakaista 150–1400, fb_frac 0.45) — roadmap: z-profiilipohjainen haku.
- **Trim ei saa kutistaa rajattomasti** (`_trim_endpoints`, `_MAX_TRIM` 300/pää):
  datattoman seinän ±30 mm kaistaan osuu vain RISTEÄVIEN seinien pisteitä
  risteyskohdissa → 2/98-percentiilit romahduttivat 4.0 m perimetriseinän
  79 mm:iin. Jatkolla oli cap alusta asti — kutistus unohtui.
- **Nurkkasulku ei saa kutistaa seinää** (`close_open_corners`,
  `_CLOSE_MAX_SHRINK` 300): leikkauspiste syvällä janalla = T-liitos keskellä
  seinää, ei nurkka. Ilman vahtia kaksi eri paria veti saman seinän molemmat
  päät samaan pisteeseen (2.8 m → 0 mm) ja 0-tyngät myrkyttivät seuraavat passit.
- **Dangling-pää joka YLTÄÄ toiseen seinään ei ole irrallinen**
  (`_end_reaches_wall`, reach 2.3 m = `_CLOSE_MAX_EXT`): aidon seinän naapurit
  voivat puuttua detektiosta → molemmat päät "ilmassa" vaikka close_open_corners
  yhdistäisi ne myöhemmin. Ilman tätä 1.6 m GT-seinä poistui.
- **Lattiakontuureja voi olla monta** (`detect_floor_contours`): paksun seinän
  takainen huone on OMA polygoninsa — pelkkä suurin kontuuri → toinen asunto ei
  koskaan saanut perimetriä eikä sulkeutunut tilaksi. Kaikki ≥1.5 m² alueet käsitellään.
- **QA:n ja linjauksen on mitattava RAAKAA pilveä, ei suodatettua** — 12 mm
  voxel + PointNet piilotti 21 mm pintavirheen (QA väitti 0.2 mm; lämpökartta
  raakaa vasten paljasti). `run_floors` lataa 5 mm refine-pilven; QA-raportti ja
  `_align_faces_to_surface_median` käyttävät sitä. Todellinen mittari on AINA
  `_tol_heatmap.py` raakapilveä vasten.
- **Epäsymmetrinen näkyvyys rikkoo parikynnyksen**: takapinta kauempaa skannattuna
  on ~10–30 % etupinnan tiheydestä → 25 % piikkikynnys hylkää AIDON pinnan ja
  yksipinta-polku lukitsee väärin. Heikko piikki (≥`_TL_WEAK_FRAC` 8 %) kelpaa
  jos se istuu odotetun vastapinnan kohdalla (±60 mm). Rohbaun 219 mm seinä
  varmistettiin GT-labeleista (molemmat pinnat 100 % Wall).
- **Toimituspaksuus-snap vain ±12 mm sisältä** (`_STD_SNAP_TOL`): 215 mm
  betoniseinä pakkosnapattuna 200:aan vie pinnan 9.5 mm pieleen — 1.5 mm
  pintalupaus voittaa siistin paksuuslistan kun todellisuus poikkeaa selvästi.
- **Pinnaton kaista = fiktioseinä, flägää älä linjaa**: jos dominantin puolen
  MAD > 20 mm, kaistassa on massaa (telineet/tavara) muttei seinäpintaa —
  mediaanilinjaus olisi fiktiota → confidence ×0.5 (perimetri 0.5→0.25 < 0.4
  → QA:n TARKISTA-lista).
- **Perimetriseinän sijaintiprior on heikko**: lattiakontuurigrid (25 mm ruutu +
  3 px dilaatio) tuottaa kymmenien mm systemaattista biasta → linjauskorjaus
  floorplan-seinille max 90 mm (mitatuilla 25 mm pitää — niiden akseli on jo oikein).
- **Suodattimen maskinsiirto EI saa käyttää o3d:n voxel_down_samplea** — o3d:n
  grid on eri origossa kuin oma hash → sentroidi putoaa naapurisoluun ja
  tasopinnoilta katosi 20–30 % pisteistä avainhaussa (Wall 89 % → 66 %).
  Tämä oli tuotannossa v0.5.0:sta asti ja söi seiniä salaa. Oma grid molempiin
  suuntiin (`unique(return_inverse)`) → piste perii täsmälleen voxelinsa päätöksen.
- **Laattakaistat (lattia/katto ±90 mm z-piikeistä) pakkosäilytetään** ennen
  suodatusta — rouhea työmaaholvi luokittui 55 % roskaksi ja slab/perimetri
  näki nälkää. Poisto ei ole koskaan oikein.
- **Pilarit: pystypeitto, EI DBSCAN** (`column_detector`): työmaalla holvituet/
  tavara ketjuttavat pilarin ympäristöönsä (eps-ketju) → jättiklusteri → 0/92
  GT-pilaria. Solu jonka z-binit täynnä lattia→katto = ehdokas; ohut tuki putoaa
  minimimittaan, seinänpala rengastestiin (linjassa lisää täyttösoluja).
- **Valepilarit/-palkit sotkuisissa skanneissa: poikkileikkauksen vakaus +
  irrallisuus + headroom** (mitattu 3DSES-vuotoskannista: 3 valepilaria + 1
  valepalkki vuotorajan rykelmästä, läpäisivät vanhat rengas/ympäröinti-testit
  koska eivät ole ULKOreunalla vaan sisärajalla). Erottimet: (1) pilarin XY-
  poikkileikkaus ~sama joka korkeudella (kaluste heiluu 35↔500 mm); (2) vyötärö-
  korkeudella (1–1.8 m) ympärillä ilmaa (aito ≤4/16 suuntaa täynnä, kaappi 8/16);
  (3) palkin ALLA tyhjää (aidon alta kävelee, kalusteen päällä istuva klusteri
  tukossa; vain valmiissa tilassa). **Rajallisuus:** täyskorkea IRRALLINEN kaappi
  jolla on vakaa poikkileikkaus on geometrisesti identtinen pilarin kanssa — sitä
  ei erota ilman semanttista tietoa (jää confidencellä; QA:n TARKISTA-lista).
- **Georef: geometria PYSYY skannin oikeissa koordinaateissa, ei origo-siirtoa**
  (`ifc/crs.py`). Radikal katsoo malleja Cintoossa pistepilveä vasten → Cintoo
  sijoittaa IFC:n sen RAAKAGEOMETRIAN koordinaateilla, joten overlay vaatii isot
  oikeat koordinaatit. Origo-siirto (geometria lähelle nollaa) rikkoisi tämän.
  `IfcMapConversion` on VAIN metatietoa Revitille (shared/survey coords); offset
  = 0 (geometria kantaa jo koordinaatin). **Yksikköansa:** geometria on mm mutta
  projisoidut CRS:t metreissä → `Scale = 0.001` (mm→m), muuten Revit sijoittaisi
  1000× väärään paikkaan. Oletus EPSG:3067; `config.crs_epsg` yliajaa.
- **Kerros jossa <2 % pisteistä on haamu** (skannerin harhat rakennuksen alla)
  — tuotti tyhjän IFC:n floor_00:na. Korkea viipale (> 4.6 m) ilman tyhjää
  z-kaistaa jaetaan sisäisen laattapiikin kohdalta (portaikko yhdistää tasot,
  muuten `_floor_ceiling` ottaa väärän katon ja 55 %-maski tappaa kaikki seinät).
- **Mallikoulutuksen seesaw**: pelkkä Rohbau-koulutus tuhosi asuntosuodatuksen,
  roskapainot ×3 tuhosi työmaarakenteen (89 → 61 %). Checkpointit AINA talteen
  versioittain ennen export_onnx:ää (se ylikirjoittaa .pth:n!). Aktiivinen malli
  varmuuskopioidaan ennen korvaamista, ja korvaus vain jos KOKO gauntlet
  (asunto + talo35 + rohbau keep-ratet) on vihreä.
- **Iso tila EI ole kasvo jota suodattaa — sitä ei ole olemassa.** Seinärengas ei
  sulkeudu isossa tilassa (mitattu: 72×48 m myymälä → 3 kasvoa, 150×100 m → 0 tilaa;
  perimetri pirstoutuu, itäseinä 5 palana, suurin rako 5.3 m). `_COLIN_GAP_MM`:n
  (450 mm) nosto on VÄÄRÄ korjaus — se yhdistäisi aitoja oviaukkoja. Ratkaisu:
  lattiakontuuri (`detect_floor_contours`) syötetään `detect_rooms`:iin renkaana.
  **Kaksi ansaa jotka piti mitata ennen kuin se toimi:**
  (1) Kontuuri kulkee seinän ULKOpinnan tasalla (mitattu 260 mm keskilinjojen
  ulkopuolella) → sellaisenaan seinäviivat jäävät KELLUMAAN renkaan sisään, eivät
  solmitu siihen, iso kasvo saa reiät ja putoaa ulkokehänä. Reunat on kohdistettava
  vastaavien seinien keskilinjoille ensin (`_snap_ring_to_walls`). Testi joka käytti
  rengasta seinien PÄÄLLÄ meni läpi eikä paljastanut tätä — käytä oikeaa offsettia.
  (2) Kontuuri saa vain TÄYDENTÄÄ, ei leikata: sen sijaintiprior on heikko, ja
  seinien rajaamiin tiloihin päästettynä se pudotti asunnon huonealan
  55.73 → 53.62 m² (−3.8 %). Tilat lasketaan ensin pelkistä seinistä; kontuurin
  kasvoista otetaan vain kattamattomat (≤10 % päällekkäisyys) ja niille on
  KORKEAMPI rima (≥6 m², ≥1.2 m leveä) — muuten väärin sijoittuneen
  perimetriseinän viereen syntyy 0.86 × 2.54 m "huone" (mitattu apt2).
- **ASUNTOKOOSTA JOHDETTU VAKIO ON MITTAKAAVA-ANSA.** `room_detector._MAX_AREA`
  oli 90 m² ("tätä suurempi = koko asunnon ulkokehä") → 3456 m² myyntialue ei
  voinut koskaan tulla tilaksi. Oikea tunniste sille mitä sääntö yritti torjua on
  `len(poly.interiors) > 0`: polygonize palauttaa ulkokehän REIÄLLISENÄ. Samalla
  paljastui että `Space.boundary` rakennettiin `.exterior`-renkaasta → ala
  kirjautui 80 m² kun kasvon oikea ala oli 71 m². **Kun jokin raja on absoluuttinen
  mm²/mm-luku, kysy mistä rakennuskoosta se on peräisin.**
- **Yksipuolisen seinän akselia ei kiinnitä mikään** — `_align_faces_to_surface_median`
  MITTASI virheen oikein ja jätti korjaamatta 25 mm cappiin (cap olettaa akselin
  olevan jo ~oikein, mikä pätee vain kaksipuoliselle jonka kaksi pintaa kiinnittävät
  sen). Mitattu synteettisellä 72×48 m myymälällä: 72 m ja 21 m ulkoseinä 57.4 ja
  62.1 mm pinnastaan, ja **putken oma QA väitti 22/24 seinää ≤1.5 mm** — vain
  `_tol_heatmap` paljasti sen. Cap nousee kaistan reunaan vain kun vastapinnalla on
  <10 % dominantin pisteistä JA dominantti puoli on yksi tiivis taso (≥80 % ±30 mm
  mediaanista). Kaksipuolisella cap pysyy 25 mm:ssä (iso siirto = väärä pinta).
  Korjauksen jälkeen kaikki 24 seinää ≤0.4 mm.
- **Maski ei voi mitata omaa pikselikokoaan hienompaa paksuutta**: yksipuolisen
  pinnan viivan kontuuri kiertää sen MOLEMMILTA puolilta ja `_merge_axis_lines`
  lukee reunat kahdeksi pinnaksi → 66–92 mm "paksuus" vaikka pintoja on yksi.
  Aidon 66 mm väliseinän kaksi pintaa taas sulautuvat maskissa yhdeksi viivaksi.
  Kumpikaan ei siis anna paksuutta → alle 4 × pikselikoon jäävä spread hylätään ja
  siemeneksi tulee `_DEFAULT_THICKNESS`; oikea arvo mitataan raakapisteistä.
  **Yksipuolisen seinän paksuus jää silti arvaukseksi** (fysikaalinen raja) —
  vain PINTA on oikein.
- **Diagnostiikkaraportti** (`qa/diagnostics.py`): joka ajosta `diagnostics.txt`
  output-hakemistoon (versio, ympäristö, vaihelokit, virhe) — pilottiasiakas ei
  voi jakaa skanneja, tämän voi. Ei koordinaatteja.

## Tunnetut rajoitukset

- **Kattavuuden katto on PYSTYMASKISSA, ei sen jälkeisessä ketjussa.** Mitattu
  Rohbau site_07/scene_07000: maski 8031 px ≈ 36 m seinää → 60.3 m segmenttejä
  (molemmat pinnat) → 14 seinää. Muunnos on tehokas; maski päästää läpi vain
  47.7 % aidoista seinäpikseleistä. **Kolme korjausyritystä KUMOTTU mittauksella
  — älä toista:** (1) `_VSLICE_MIN_PER` 2→1 ei vaikuta (p50 9→8);
  (2) semanttinen `pred==wall`-maski tuo 263 k palkkipistettä 276 k seinäpisteen
  rinnalle, koska malli **ei ennusta beam-luokkaa lainkaan** (romahtanut
  ceiling/floor/wall/column/clutter-viisikkoon); (3) maskin morfologinen siivous
  huonontaa kaikilla varianteilla (nykyinen 60.3 m → open3+close9 39.3 m →
  open5 0 m) koska 200 mm seinä on vain ~7 px leveä ja opening syö sen.
  **Ainoa mitattu polku ylös:** pystyjakso ≥1000 mm JA `pred==wall` yhdessä →
  65.3 % seinäpikseleistä 2.6 % palkkikontaminaatiolla (vs 47.7 % / 2.0 %).
  Vaatii labelit suodattimelta detektorille; `PointNetFilter.predict_classes`
  on jo olemassa, mutta labelit on laskettava SUODATETULLE pilvelle.
- **KATTAVUUS on nyt suurin puute, ei tarkkuus** (mitattu Rohbau3D-GT:llä,
  site_07/scene_07000): mallin seinäpintojen alla olevista pisteistä **96.2 %**
  on aidosti GT:n Wall/Drywall — jokainen detektoitu seinä 96–100 %. Mutta
  GT-seinäpisteistä vain **26 %** on jonkin mallin seinän kaistassa: kolme
  neljäsosaa aidoista seinistä jää mallintamatta. Kaikki 5 ongelmaseinää olivat
  **perimetriseiniä**: kaksi 100 % Beam (palkista tehty seinä), kolme tyhjää/None.
  Rohbaussa löytyi 0 ovea vaikka GT:ssä on 37 828 oviaukkopistettä.
- **Rohbau3D:n asemat eivät ole keskenään hyvin rekisteröityjä** (mediaani
  lähimpään naapuriin 222–493 mm asemien välillä). 5 aseman yhdistäminen SOTKEE
  pinnat: yksi scene → 14 seinää, viisi yhdistettynä → 0. Aja Rohbau
  **scene kerrallaan** tai `icp_refine=True`. Testidata ei ole gitissä
  (`data/_rohbau/`, lataa open-data.unibw.de doi:10.60776/ZWJFI4, MIT).
- **PointNet-suodatin yleistyy paljaaseen betonirunkoon** (mitattu Rohbau-GT:llä):
  Wall 99.8 %, Drywall 99.1 %, Ceiling 99.8 %, Column 99.9 %, Floor 97.2 %,
  Beam 67.5 %, **TGA 10.2 %** (talotekniikka pois, oikein). Kokonais-keep 0.839.
- **Pipeline on viritetty yksikerroksiselle tilalle** (yksi lattia + yksi katto).
  Monikorkuinen tila (esim. 3DSES-koulu, 7 m porras) rikkoo globaalin korkeuden →
  seinät väärään korkeuteen. Per-huone-korkeus on roadmapilla.
- **Yksipuolisten (ulko)seinien paksuutta/sijaintia ei voi mitata** — vain sisäpinta
  keilattu. Fyysinen raja, ei bugi.
- **Occluusio** (kalusteet nurkissa) rajaa nurkkasijainnin ~100 mm:iin kalustetulla
  datalla. Puhtaalla rungolla sama pipeline antaa ~mm.
- **LIIKETILA, mitattu synteettisellä 72×48×7 m myymälällä** (`data/_synth_retail.py`,
  8.2 M pistettä, GT tunnettu). Hyvin: kaikki 9 GT-seinää löytyi, jokainen 24
  seinästä ≤0.4 mm pinnastaan (`_tol_heatmap`), sisäseinien paksuus täsmälleen
  oikein (120/200 mm). Auki:
  1. **Lattia-katto-hyllykkö tuottaa 44.8 m valeseinän** — semanttinen suodatin
     poisti vain 6 % pisteistä eikä tunnistanut hyllykköä. Geometrisesti hyllykön
     etupinta ON seinä; ero on vain semanttinen.
  3. **Pilareita 24/34**: puuttuvat ovat täsmälleen ne joiden vieressä (320 mm)
     seisoo gondoli → `column_detector`:n vyötärökorkeuden (1–1.8 m) irrallisuustesti
     kaatuu. Liiketilassa hylly pilarin vieressä on normaalia, ei poikkeus.
  4. Yksipuolisten ulkoseinien paksuus 66–92 mm (todellinen 250) — pinta on oikein,
     paksuutta ei voi mitata.
- **Liiketilojen hyllyt** (lattia-katto) läpäisevät geometrisen pystymaskin →
  semanttinen suodatin tarvitaan. **`pointnet-retail` on nykyään ALIAS
  `pointnet`:lle** — erillinen liiketilamalli sulautettiin yhteen malliin
  (cb50610, geocol_v2_ms: hyllynpoisto 15 % → 71 %, Rohbau-rakenne
  0.879 → 0.947, monikerros korjattu). Molemmat `.onnx`-tiedostot ovat
  tarkoituksella identtiset; älä oleta moodien suodattavan eri tavalla.

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

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
| `data/_scale_run.py` | Tuotantoajo jossa **aika ja huippumuisti vaiheittain** (`psutil`-näytteistys + progress-merkit). Tulostaa myös **missä vaiheessa huippu syntyi** — pelkkä luku ei kerro mitä korjata. `--voxel` pakottaa detektiovoxelin |
| `data/_mem_probe.py` | Muistin **erittely askeleittain**: RSS askeleen jälkeen JA askelhuippu (0.2 s näytteistys). Transientti ei näy jälkikäteen luetusta RSS:stä — `column()` käy 2.9 GB:ssä viidessä sekunnissa. `--real` ajaa oikean `filter_with_labels`-kutsun |
| `data/_filter_equiv.py` | **Suodattimen tulos tarkistussummina** (pidetyt pisteet, labeliavaimet+arvot, per-piste-luokat) → optimoinnin tuloksettomuus todistetaan `git checkout` -vertailulla, ei päättelemällä |
| `data/_voxel_curve.py` | Montako pistettä jää milläkin voxelilla — paljastaa milloin voxelointi on **no-op** (pilven pisteväli > voxeli) |
| `data/_col_probe.py` | **Mikä portti hylkää minkäkin GT-pilarin.** `cache` tallentaa `detect_columns`:n syötteet kerran (~9 min), `gates` tutkii portit sekunneissa — porttien säätö ei vaadi putkiajoa |
| `data/_col_view.py` | **Pilariehdokas kuvina**: XY vyötäröltä, XY katon alta, pystyleikkaus. Erottaa hormin kaapista ja seinän paksunnoksen aidosta pilarista, kun mittaluvut eivät riitä |
| `data/_room_probe.py`, `data/_frag_probe.py`, `data/_tl_probe.py` | Miksi tila hylättiin / onko perimetri pirstoutunut / miten paksuus syntyi |
| `data/_evidence_probe.py` | Ehdokasmittarit per seinä (pintapeitto, kohina, mitä pinnan takana on) **GT-labeloituna** myymälän `shelf_faces`-totuutta vasten — kertoo erotteleeko mittari ennen kuin se viedään tuotantoon |
| `data/_evidence_gt.py` | Sama Rohbau3D:n per-piste-GT:tä vasten: jokaiselle detektoidulle seinälle kaistan GT-luokkajakauma **ja** ehdokasmittarit rinnakkain → kynnys valitaan mitatusta välistä |
| `data/_vprofile_probe.py` | Seinän PYSTYPROFIILI ja VYÖTÄRÖN JATKUVUUS GT-luokan rinnalla — tällä mitattiin että pystyprofiili ei erottele palkkilinjaa mutta jatkuvuus erottelee 7-kertaisella marginaalilla |
| `data/_ctrl_contour.py` | Kontrolliajo: iso+korkea → histogrammi -auto-reititys patchattuna pois |
| `data/_prune_probe.py` | Seinän tuki, jatkuvuus, offset, **vastineen jatkuvuus** ja GT-luokka rinnakkain — tällä erotettiin haamu siirtyneestä seinästä |
| `data/_ctrl_waist.py` | Kontrolliajo: `_nearest_surface` palautettuna koko korkeuden hakuun → mitkä seinät vyötärörajaus poistaa LISÄÄ |
| `data/_density_probe.py` | **Kestääkö mittari harvan skannin**: harventaa saman pilven 1/1…1/5000 ja ajaa tuen, jatkuvuuden ja karsinnan uudelleen. Erottaa oikeat poistot (GT-haamut) vääristä |
| `data/_gap_probe.py` | **Mikä jää mallintamatta**: ryhmittelee lunastamattomat GT-seinäpisteet paloiksi ja tulostaa ne kokojärjestyksessä — kertoo onko vaje kokonaan puuttuvia seiniä, päitä vai sirontaa |
| `data/_gap_view.py` | Sama kuvana: lunastettu (harmaa) vs puuttuva (punainen) GT-seinäpiste mallin akselien päällä |
| `data/_rohbau_all.py` | **Yleistyvyys**: ajaa kaikki Rohbau-scenet erikseen ja tulostaa kattavuuden, tarkkuuden ja ongelmaseinät rinnakkain — kynnykset on viritetty vain sceneen 07000 |
| `data/_second_face_probe.py` | **Keksiikö katvepintahaku seiniä**: ajaa aineistot joilla ei ole GT:tä ja tulostaa löydetyt katveseinät tuki/jatkuvuus-lukuineen |
| `data/_shelf_gt_probe.py` | Mitä `remove_shelf_front_walls` oikeasti poistaa — poistettujen GT-luokkajakauma Rohbaussa |
| `data/_cont_rule_probe.py` | Vertaa jatkuvuussääntöjä (kiinteä 5 / ≥1 / suhteellinen) eri tiheyksillä ja tulostaa erottelun aito−palkki — tällä valittiin suhteellinen sääntö |
| `data/_ctrl_snapgate.py` | Kontrolliajo: napsautusportti vanhalla (`support == 0`) vs nykyisellä ehdolla, seinien akselit ja GT-luvut rinnakkain — tällä eristettiin kaksi regressiota |
| `data/_lobby_ab.py` | Aulan A/B: auto-reititys vs pakotettu contour, kuva + mitatut tuki/jatkuvuus-luvut. `--plot-only` piirtää uudelleen ajamatta putkea |
| `data/_lobby_cov.py` | Sama A/B kahdesta suunnasta **ilman GT:tä**: tuki (tarkkuuden suunta) ja kaistan lunastettu osuus (kattavuuden suunta), nimittäjä sama molemmille |
| `data/_wall_view.py` | **Liputettu seinä kuvina**: XY vyötäröltä, poikkileikkaus, mallin pinnalla olevat pisteet. Erottaa HAAMUN (ei mitään) VÄÄRÄSSÄ PAIKASSA olevasta (pinta on, mutta sivussa) — pelkkä `support`-luku ei kerro kumpi |
| `data/_img_openings_qa.py` | Kuvaohjattu aukkodetektio oikealla kuvallisella E57:llä; vertaa vanhaan moduuliin samoilla seinillä+pilvellä |
| `data/_cov_check.py`, `data/_support_verify.py` | Pintatuki mille tahansa mallille (väärät hälytykset) / tuotantototeutus vs. koetin samoilla luvuilla |

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

- **"Kuvaohjattu" aukkodetektio EI käytä kuvien pikseleitä.** `image_openings.py`
  päättää kokonaan pistepilven syvyyspuskurista: näkeekö skannerin säde
  seinätason ohi. Kuvia tarvitaan vain skanneriasemien SIJAINTIIN (pose) ja
  piirteen porttina (`.e57` + `images2D`, muuten no-op). Todennettu
  korvaamalla panoraama mustalla 4×8-kuvalla → sama aukko, samat mitat.
  Älä siis lisää siihen kuvapohjaista logiikkaa olettaen että panoraama on
  jo olemassa — sitä ei enää rakenneta (maksoi 15.9 s / 285 kuvaa).
- **`confidence` EI kelpaa laatusignaaliksi — se on kokoproxy.** `wall_contour`
  antaa `0.80 + pituus/20000`, `wall_density` `pituus/5000`, aukot
  `leveys × korkeus`, laatat pinta-alan. Siis **mitä pidempi elementti, sitä
  korkeampi luottamus** — ja pahimmat valeseinät ovat pitkiä: myymälän 44.7 m
  hyllyvaleseinä saa 1.0, mallin alin arvo on 0.862 ja QA:n kynnys 0.40.
  Seuraus: liiketilamalleissa TARKISTA-lista oli tyhjä vaikka virheet tiedetään.
  Elementin epäilyttävyys on **mitattava pilvestä** (`Wall.support` = kuinka
  suuri osa pinnasta on keilattu), ei kysyttävä detektorilta joka sen loi.
  Poikkeus: `column_detector`:n luottamus (kompaktius × pistemäärä) on aitoa
  evidenssiä — se saa jäädä.
- **Palkkilinjan erottaa VYÖTÄRÖN JATKUVUUS, ei pystyprofiili.** Histogrammi
  tekee palkiston keskikorkeuden tiheydestä 28 m "seiniä". Niillä on pisteitä
  joka korkeudella (lattia, katto, palkki, pilarit), joten pintatuki ja
  pystyprofiili eivät auta — **pystytuki erottelee jopa VÄÄRÄÄN suuntaan**
  (palkkiseinät 0.92–1.00, aidot 0.63–0.94). Toimiva mittari on pituussuuntainen
  jatkuvuus 30–70 % korkeudella, 500 mm sarakkeina: aidot 0.50–1.00,
  palkkiseinät 0.05–0.07 (Rohbau-GT). `Wall.continuity`, kynnys 0.30.
  Oviaukko ei riitä pudottamaan aitoa seinää alle (testattu).
- **ABSOLUUTTINEN pistemäärä kynnyksenä sitoo mittarin keilaustiheyteen — ja
  harvalla skannilla se POISTAA aitoja seiniä.** Jatkuvuus vaati 5 pistettä /
  500 mm sarake. `data/_density_probe.py` (sama pilvi harvennettuna): karsinta
  murtui **1/250:llä** ja poisti kaksi GT-aitoa seinää; `data/_cont_rule_probe.py`
  näytti syyn — erottelu aito−palkki romahti **0.94 → 0.00**, kun suhteellinen
  sääntö (≥ 10 % sarakkeiden keskiarvosta) piti sen **0.79**:ssä. Korjattuna
  0 väärää poistoa aina **1/5000** asti (5 465 pistettä koko 822 m² kohteelle).
  Kolme sääntöä joita kannattaa soveltaa kaikkiin uusiin mittareihin:
  1. **Kynnys suhteessa dataan, ei absoluuttiseen pistemäärään.**
  2. **"Liian vähän dataa" ei saa palauttaa samaa arvoa kuin "todistetusti
     huono"** — jatkuvuuden `0.0` oli karsintakäsky; nyt epävarma on `None`,
     jolloin elementti jää tarkistuslistalle eikä poistu.
  3. **Kun mittari ei voi todistaa mitään, älä anna sen päättää.** Alle 4 m
     seinässä on liian vähän sarakkeita; sen kohtalo ratkaistaan sillä onko
     paikalla MITÄÄN (pisteet ±1 m vyötäröllä). Se on tyhjä vs ei-tyhjä eikä
     tiheyskynnys: Rohbaun haamuilla 0 joka tiheydellä, aidoilla lyhyillä
     63 754 / 46 581 → 36 / 27 vielä 1/2500:lla.
- **Kontuuri näkee vain ENSIMMÄISEN pinnan — mikään detektorin kynnys ei tuo
  sen takana olevaa seinää.** `cv2.findContours` jäljittää vapaan tilan reunan,
  joten puolen metrin päässä perimetristä seisova kipsiseinä on maskin sisällä
  eikä sitä ole olemassa mallille. Rohbaussa se oli **suurin yksittäinen
  kattavuusvaje**: 20,6 %:n vajeesta 52,6 % istui 400–700 mm päässä
  mallipinnasta (`data/_gap_probe.py`), ja GT:ssä ne ovat omia
  Drywall-instanssejaan. Korjaus on oma vaihe (`semantics/second_face.py`,
  0.792 → 0.887), ei detektorin viritys. **Vaihe ajetaan VASTA karsinnan
  jälkeen**: hyllynetupinta-poisto, dedup ja napsautus pitävät rinnakkaista
  seinäparia virheenä, ja ensimmäisessä yrityksessä ne söivät molemmat
  (30 m emäseinät katosivat kokonaan).
- **Yksi kohde ei kerro yleistyykö putki — aja `data/_rohbau_all.py`.** Kaikki
  kynnykset on viritetty `scene_07000`:sta. Kun neljä muuta sceneä ajettiin
  ensimmäistä kertaa (16.8.), kattavuus piti (0.807–0.887) mutta katvepintahaku
  teki kahdessa valeseinän VÄLIPOHJAN REUNASTA. **Uusi sääntö ei ole valmis
  ennen kuin se on nähnyt muutakin kuin viritysaineiston.**
- **Nurkkasnäppäys venyttää seinää evidenssin yli — ja venytys joka EI osu
  mihinkään on pelkkä virhe.** `_MAX_EXTEND` (1300 mm) ja `_CLOSE_MAX_EXT`
  (2300 mm) ovat puhtaasti geometrisia rajoja; kumpikaan ei kysy onko
  venytetyllä osalla pisteitä. Asunnossa se tuotti 3.8 m seinään 1.4 m ilmaa.
  **Erottava todiste ei ole hännän pituus vaan se osuuko pää mihinkään:**
  venytys nurkkaan on laillinen mallinnusvara, roikkuva häntä ei — ja asunnon
  venytetyt päät olivat yhä 542 mm ja 495 mm irti. `semantics/overstretch.py`
  leikkaa vain kattamattoman JA irrallisen pään, joten suljettu nurkka ei voi
  avautua. Kontrolli: 6.2 m leikattu viidessä Rohbau-scenessä, kattavuus ja
  tarkkuus muuttumattomat — GT-pisteistä poistui 65 kpl 594 000:sta.
  **Älä leikkaa nurkkaan osuvaa päätä pelkän katteen perusteella:** asunnon
  wall_005:n 800 mm häntä päättyy aitoon nurkkaan (vastinseinä on katettu
  liitoskohdassa), ja sen trimmaus avaisi huonepolygonin.
- **Betonirungossa laatan reuna on "parempi seinä" kuin seinä.** Tuki 0.80–0.82
  ja jatkuvuus 0.89–0.97, kun aidoilla kipsiseinillä 0.40–0.82 → laatukynnyksen
  nosto poistaa aidot ja säästää väärät. Erottava todiste on ALAREUNASSA:
  laatan reunan alla vaakataso jatkuu pinnan MOLEMMIN puolin, seinä katkaisee
  sen. Mitattu 7 ehdokkaasta: 0.92 molemmilla palkkilinjoilla, 0.00 kaikilla
  viidellä aidolla. **Varmista että testillä on dataa** — ensimmäinen versio ei
  purrut, koska ±1.5 m hakuikkuna loppui juuri ennen: 1.5 m päässä olevalle
  ehdokkaalle jäi 15 mm käytettävää sivuulottumaa.
- **Hyllyn etupinta ja kipsiseinä ovat geometrisesti sama asia — erottava
  todiste on VÄLISSÄ, ei pinnassa.** Molemmat: lattiasta kattoon ulottuva
  yhtenäinen pystypinta 0,5–1 m emäseinästä. Tuki, jatkuvuus ja välin
  pistemassa eivät erottele (mitattu: väli/pinta 0.038 vs 0.042 — sama).
  Erottelija on välin **z-rakenne**: synteettisen myymälän hyllyvälissä 6
  vaakatasoa ~900 mm välein, Rohbaun kipsiseinän välissä 1 (palkki).
- **Väärä korkeus tekee jokaisesta pystymittarista hölynpölyä.** Uusi seinä ei
  peri emäseinänsä korkeutta: 10 m hallin vyötärökaista (30–70 %) osuu 3 m
  kipsiseinän yläpuolelle, jolloin aidon pinnan jatkuvuudeksi mitataan 0.42.
  Mittaa korkeus pinnasta itsestään (sarakkeiden mediaani-ylä- ja alareuna) ja
  vaadi ≥ 20 % kerroskorkeudesta — muuten 1,1 m korkea kanavalinja pääsee läpi
  seinänä täydellisillä luvuilla (tuki 0.96, jatkuvuus 0.96; tarkkuus 0.884).
- **"Yhtä pitkä pinta" ei ole sama kuin "yksi seinä".** Sohva + kaappi + komero
  peräkkäin tuottavat 8,5 m yhtenäisen linjan, jonka tuki (0.31) ja jatkuvuus
  (0.47) ovat PAREMMAT kuin Rohbaun aidoilla kipsiseinillä (0.21/0.42). Erottava
  mittari on sarakkeittaisen ylä- ja alareunan hajonta: aito 4–9 mm (0.00 ×
  korkeus), huonekaluketju 1649 mm (0.61 ×). Rajaa lattia ja katto pois ennen
  mittausta — muuten laatat täyttävät joka sarakkeen ja reuna näyttää
  täydelliseltä kaikkialla (IQR 2 mm huonekaluketjullekin).
- **Siirron saa hyväksyä vain jos MITATTU tuki paranee — "lähin tiheä huippu"
  ei ole sama kuin "oikea paikka".** Napsautusportin levennys `support == 0` →
  `< 0.50` (tarpeen, koska aulan `wall_007` on 842 mm sivussa mutta sitä
  raapaisee jokin, tuki 0.17) regressoi Rohbaun **0.792/0.918 → 0.749/0.905**.
  Kaksi eri juurisyytä, molemmat mitattu `data/_ctrl_snapgate.py`:llä:
  (1) **lyhyt seinä ei voi todistaa vastinettaan** — 500 mm sarakkeilla 1.0 m
  seinään mahtuu kaksi saraketta, joten jatkuvuusehto 0.80 täyttyy millä
  tahansa läiskällä, ja GT-aito `wall_ext_011` hyppäsi 400 mm oman tukensa
  pudotessa 0.212 → 0.155 (`_SNAP_MIN_COLS` = 8 ≈ 4 m);
  (2) **hyvin tuettu seinä löytää huipun viereltä** — GT-aito 28 m `wall_008`
  (tuki 0.372) siirtyi 138 mm pois oikealta paikaltaan.
  Ratkaisu kohtaan 2 EI ole uusi tukikynnys (ne eivät siirry aineistosta
  toiseen) vaan **ennen/jälkeen-vertailu samasta pilvestä**: siirto tehdään
  vain jos tuki paranee ≥ 0.10. Rohbau palautui bitilleen ennalleen ja aulan
  `wall_007` nousi 0.17 → 0.51. Yleistys: kun korjaus siirtää geometriaa,
  mittaa lopputulos molemmissa asennoissa — älä luota siihen että ehto joka
  löysi kohteen osaa myös sijoittaa sen.
- **Etäisyys "lähimpään pintaan" on mitattava VYÖTÄRÖLTÄ, muuten lattian roina
  antaa haamullekin osoitteen.** `_nearest_surface` erottaa SIIRTYNEEN seinän
  HAAMUSTA, ja `prune_unsupported_walls` säästää kaiken minkä offset ≥ 250 mm.
  Koko korkeudelta haettuna histogrammin argmax osui 10 m kerroksessa lattiaan
  ja kattoon: Rohbaun `wall_ext_001` sai offsetin 442 mm ja `wall_ext_007`
  825 mm, vaikka **kummallakaan ei ollut yhtään pistettä vyötärökorkeudella**
  (GT: molemmat TYHJÄ, puhtaus 0.00) — eli siirtymäraja suojasi juuri ne jotka
  sen piti paljastaa. Vyötärökaistalla (30–70 %) ero on karkea: aito lyhyt
  `wall_ext_008` 63 754 pistettä, haamut 0. Lisäksi huipulta on vaadittava
  jatkuvuus, koska metrin roinakasa 24 m seinän vieressä riittää muuten
  antamaan uskottavan offsetin (275 mm). **Sama kaista kaikkiin kolmeen**
  (tuki, jatkuvuus, pintahaku) — `_WAIST_LO`/`_WAIST_HI`.
- **Pintatuki näkee vain PUUTTUVAN pinnan, ei väärälle pinnalle osunutta
  seinää — ja KYNNYS ON VALIDOITAVA UUDELLEEN KUN DETEKTORI MUUTTUU.**
  Kynnys 0.15 johdettiin v0.9.0:n Rohbau-mallista, jossa valeseinät olivat
  aidosti tyhjiä (aidot 0.289–0.485, valeet 0.016–0.063 → 6/6). v0.9.18:n
  malli samasta datasta tuottaa eri virhepopulaation: kuusi 28 m seinää
  PALKKIEN päällä (GT-puhtaus 0.03–0.11), ja koska palkki on aito keilattu
  pinta, niiden peitto 0.179–0.248 menee päällekkäin aitojen 0.212–0.427
  kanssa — **mikään kynnys ei erota niitä**, ja sääntö putoaa 2/8:aan.
  Virhepopulaatio vaihtuu detektorin mukana; mitattu erottelu ei siirry
  versiosta toiseen ilman uutta ajoa. Sama juurisyy kuin hyllyfrontissa:
  pinta on oikea, paikka on väärä. Sen näkee vain semantiikka (palkkiluokkaa
  malli ei tunnista) tai konteksti.
- **PINTAKOHTAINEN mittari ei erota hyllyä seinästä — konteksti erottaa.**
  Testattu neljä (pintapeitto, pinnan kohina, mitä pinnan takana on,
  takapisteiden osuus) myymälän `shelf_faces`-GT:tä vasten: hylly osuu joka
  mittarilla aitojen seinien jakauman SISÄÄN (tuki 0.972 vs aidot 0.924–1.0).
  Hyllyn etupinta ON taso siinä missä seinäkin. Älä siis yritä ratkaista tätä
  pinnan omasta geometriasta. Toimiva erottelu käyttää SUHDETTA toiseen
  elementtiin — `remove_shelf_front_walls` katsoo onko ulkopuolella pitkä
  yhdensuuntainen perimetriseinä 300–1500 mm päässä — tai semantiikkaa.
- **Pilarin irrallisuus: VAPAA KAARI + IRTI SEINÄSTÄ, ei sektorien määrä.**
  `_waist_isolated` luki ennen montako 24 kulmasektorista on täynnä (raja 4).
  Se ei erottele mitään olennaista: myymälässä gondoli seisoo pilarin molemmin
  puolin, jolloin **aito pilari peittää 16 sektoria — täsmälleen yhtä monta kuin
  hylättävä tavaran ympäröimä kaappi**. Mitattu erottelu on kaksiosainen:
  1. **Suurin yhtenäinen VAPAA kaari** ≥45°: pilarin ohi on päästävä kävelemään.
     Aito pilari 60° (käytävä) tai 360° (vapaa); kaappi tavaran keskellä 30°.
  2. **Irtiolo seinästä** ≥250 mm ehdokkaan reunasta seinäpintaan. Pelkkä kaari
     päästää läpi seinän mutkat ja paksunnokset: niillä huonepuoli on auki 180°.
     Mitattu asunto apt2: kolme valetta väleillä −123, −40, +104 mm (kaksi siis
     seinän SISÄLLÄ); myymälän aidot pilarit ≥5420 mm.
  `_WALL_MARGIN` ei riitä tähän — se karsii vain PISTEITÄ, ja seinä jota
  seinädetektori ei napannut jää omaksi kasaumakseen.
  **Vision ratkaisi tämän**: mittaluvut eivät kertoneet olivatko asunnon
  ehdokkaat hormeja vai valeita, `data/_col_view.py` kertoi sekunneissa
  (kaikki kolme istuivat seinälinjalla, pystyleikkauksessa yhtenäinen seinä).
- **Muistihuippu on suodattimessa, ja se määrää koko tuotteen katon.** Mitattu
  150×100 m hallilla (32 M pistettä): huippu 15.9 GB, ja jokainen muu vaihe
  jäi ≤5.8 GB. Suodatin on myös 51 % ajasta. Älä optimoi muuta ennen kuin
  `_scale_run.py` sanoo huipun syntyneen muualla — **huipun ARVO ei kerro mitä
  korjata, sen PAIKKA kertoo**. **Uusintamittaus v0.9.18 (15.8.): 38.3 min /
  12.9 GB** (v0.9.0: 42.5 min / 13.1 GB) — huippu yhä samassa vaiheessa, mutta
  suodattimen osuus AJASTA on noussut 51 % → **77 %** (1767 s / 2298 s). Muut
  vaiheet ≤3.5 GB. Muisti ei siis liikkunut, ja kymmenen välissä tehtyä
  detektoriparannusta ei sitä muuta: riippuvuus rakennuksen 30 mm voxelien
  määrään on rakenteellinen, ei hukkaa.
- **Muistin syö transientti, ei residentti.** Askeleen jälkeinen RSS ei näytä
  sitä: `column()` jättää 0.37 GB mutta käy 2.9 GB:ssä, `geometric()` 2.2 GB:ssä.
  Kaksi toistuvaa syytä: (1) `.astype(np.float64)` kopioi ehdoitta myös kun
  syöte on jo float64 — käytä `np.asarray(x, dtype=...)`; (2) yhden rivin
  lauseke `np.floor((pts - o) / v).astype(np.int64)` varaa NELJÄ pilven
  kokoista välivaihetta — laske erissä.
- **Kuollut lokaali elää funktion loppuun.** `del` ei ole kosmetiikkaa isossa
  pilvessä: `vkey`, `first`, `cellid`, `cx`/`cy` istuivat 1.25 GB:n edestä koko
  inferenssisilmukan ajan. Vapauta heti kun taulukko on kuollut.
- **Suodattimen NOPEUS on inferenssissä ja se on umpikuja — kolme vipua mitattu
  ja hylätty (3.8.2026, 58 M pisteen synteettinen myymälä = 17.7 M voxelia):**
  aikajako `_classify_voxels`: **session.run 70 % (233 s / 224 kutsua)**,
  geometric 17 %, bucket/unique 12 %, column <1 %. Inferenssi on
  **muisti­kaistanleveys­sidottu**, ei säie­sidottu: intra_op 4/8/16 antavat kaikki
  ~2.5 s (S171), ja tulos on säiemäärästä riippumatta BITILLEEN sama. (1) Lohko­-
  limityksen vähennys (stride 500→1000) leikkaa 2.4×, MUTTA **keep-flip 4.9 %**
  (~870 k pistettä vaihtaa keep/remove) ja luokka-flip 30 % → limitys-äänestys
  tekee oikeaa laatutyötä, poisto rikkoo laadun. (2) **INT8 dynaaminen kvantisointi
  teki inferenssistä 8× HITAAMMAN** (325→2672 s; ORT:n ConvInteger-polku on paljon
  huonompi kuin optimoitu fp32-Conv), vaikka keep-flip oli vain 0.77 %. (3) Säie­-
  konfiguraatio: ei vaikutusta. **Älä yritä näitä uudestaan.** Ainoa jäljellä oleva
  nopeuspolku olisi arkkitehtuuriltaan kevyempi malli (uudelleenkoulutus + koko
  gauntlet) — ei mikropysäytys.
- **MUISTIN voi rajata BITILLEEN samalla tuloksella XY-kaistoittain**, MUTTA
  `point_features.geometric` käyttää **kNN:ää (k=16), ei kiinteää sädettä** →
  tiukkaa halo-takuuta ei ole. Pinnalla 16NN on ~150 mm sisällä, joten ~2 m halo
  antaa efektiivisesti identtisen tuloksen (vain äärimmäisen harvat irtopisteet
  eroaisivat — krääsää joka poistuu muutenkin). Kaistavirtaus säilyttää RNG-
  järjestyksen vain jos lohkot käydään GLOBAALISSA järjestyksessä (per-lohko-siemen
  muuttaisi otannan). Tämä on iso muutos kriittiseen `_classify_voxels`:iin →
  validoi `_filter_equiv`-hashilla ennen käyttöä; älä oleta identtiseksi.
- **Voxelointi voi olla no-op eikä kukaan huomaa.** `_auto_voxel` tähtää 4 M
  työpisteeseen mutta `_AUTO_VOXEL_MAX = 25 mm` katkaisee sen; jos pilven
  pisteväli on 35 mm, 25 mm voxel ei poista mitään (mitattu `_voxel_curve.py`:
  8→30 mm kaikki 0.99). Iso kohde ajaa 8× suuremmalla pilvellä kuin suunnittelu
  lupaa. Cap on asunto-ajalta eikä sitä ole koskaan mitattu tilanteessa jossa
  se sitoo. **Voxelinuppi ei kuitenkaan pelasta isoa kohdetta**: työjoukko
  skaalaa PINTA-ALAN mukaan, ja 4 M:ään pääsisi vasta ~110 mm:llä.
- **Optimoinnin tuloksettomuus todistetaan hasheilla, ei päättelemällä.**
  `_filter_equiv.py` + `git checkout` -vertailu nappasi oman muutokseni bugin:
  `_classify_voxels`-funktiossa oli jo muuttuja `uniq` (lohkoruudukon id:t),
  joka ylikirjoitti voxeliavaimet — 8.2 M avainta → 14 308. Testit (109 kpl)
  menivät läpi, pidetyt pisteet olivat oikein, vain labelit menivät hiljaa
  rikki. **Nimien uudelleenkäyttö pitkässä funktiossa on todellinen riski.**

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
- **Geometriaketju skannaa koko pilven per seinä → `XYIndex`.** Profiloitu (ei
  arvattu, `python -m cProfile`): 72×48 m myymälä, 8.2 M pistettä, 165 seinää →
  `_trim_endpoints` 41 s, `_surface_lock_wall` 38 s, `_refine` 19 s,
  `_fine_rotate` 15 s, `_skew_rotate` 13 s, `_segments_coplanar` 12 s,
  `_gap_has_lintel` 10 s. Indeksi (`core/geometry/xy_index.py`) rakennetaan
  KERRAN per pilvi ja palauttaa **ylijoukon** kaistan pisteistä; kutsuja soveltaa
  saman ehdon → valikoituva joukko ja sen JÄRJESTYS ovat identtiset (percentiilit
  ja mediaanit eivät muutu). Mitattu: ketju 244 → 59 s, koko ajo 11.6 → 8.5 min,
  malli bitilleen sama neljällä datalla. **`_trim_endpoints` ei saa rajata akselin
  suunnassa** — se laskee percentiilit kaikista pinnalle osuvista pisteistä myös
  janan ULKOpuolelta (siitä pidennys tulee), ja pirstoutuneessa perimetrissä
  kaukanakin oleva kollineaarinen pätkä on relevantti.
- **Semanttinen suodatin on ONNX-sidonnainen, ei numpy-sidonnainen** (profiili:
  356 s säikeiden odotusta + 54 s inferenssiä). Sitä ei nopeuteta indeksoinnilla
  eikä muutenkaan muuttamatta mallin tulosta — älä yritä.
- **Diagnostiikkaraportti** (`qa/diagnostics.py`): joka ajosta `diagnostics.txt`
  output-hakemistoon (versio, ympäristö, vaihelokit, virhe) — pilottiasiakas ei
  voi jakaa skanneja, tämän voi. Ei koordinaatteja.

## Tunnetut rajoitukset

- **`_looks_like_retail` on tosiasiassa "ISO JA KORKEA", ei liiketila.** Ehto on
  pohja-ala + vapaa korkeus ≥4.5 m; Rohbau site_07:n ~10 m betonirunko täyttää
  sen ja reitittyy histogrammidetektorille ("liiketila → histogrammi", näkyy
  diagnostiikassa). Nimi on yhä väärä, **mutta reititys ei enää maksa
  tarkkuutta** — se maksoi ennen kuin karsinta osasi erottaa palkkilinjan.
  **Mitattu uudelleen 16.8.2026 `data/_rohbau_qa.py`:llä, kontrolliajo
  `data/_ctrl_contour.py site_07 scene_07000` (auto-reititys patchattu pois):**
  | detektori | kattavuus | tarkkuus | ongelmaseiniä | (15.8. tarkkuus) |
  |---|---|---|---|---|
  | histogrammi (auto, tuotanto) | **0.887** | 0.924 | **0** | 0.510, 8 kpl |
  | contour (auto pois) | 0.653 | **0.951** | 1 | 0.951 |
  Kauppa on nyt kattavuus **+0.234** vs tarkkuus **−0.027**; ennen se oli
  +0.14 vs −0.44. Ero syntyi jatkuvuuskarsinnasta (kuusi 28 m valeseinää
  PALKEILLA, GT Beam 93–96 %, karsiutuvat nyt) ja katvepintahausta.
  **Reititystä ei siis pidä kääntää** — contour menettää kolmanneksen
  kattavuudesta eikä sen tarkkuusetu ole enää kuin 2,7 pros.yks.
  **AULA ON MITATTU (15.8.), ja siellä kauppa oli vielä huono.** Tiedosto on
  julkinen näyte (ks. testidatataulu), joten trigger ei ole enää sokea kohta.
  `data/_lobby_ab.py` + `data/_lobby_cov.py`, sama pilvi molemmille, ei GT:tä:
  | reititys | seiniä | seinäpituus | tuki med | lunastettu | tuki < 0.25 |
  |---|---|---|---|---|---|
  | auto = histogrammi | 17 | **120.9 m** | 0.41 | 0.631 | 5 kpl / **24.2 m** |
  | contour (auto pois) | 13 | 50.0 m | **0.60** | 0.564 | 2 kpl / 5.4 m |
  Histogrammi ostaa **+6.7 pros.yks. lunastettuja pisteitä 70.9 lisämetrillä**
  seinää — marginaalinen vaihtokurssi 0.09 pp/m, kun contourin oma on 1.13
  pp/m eli **12× parempi**. HUOM: aulaa ei ole mitattu uudelleen 15.8. jälkeen,
  eli nämä luvut ovat ENNEN jatkuvuuskarsintaa ja katvepintahakua, jotka
  käänsivät Rohbaun kaupan hyväksi. Aja `data/_lobby_cov.py` uudelleen ennen
  kuin nojaat näihin.
  **Mutta EI yksipuolisesti:** histogrammi löytää aulan pitkät HYVIN tuetut
  perimetriseinät jotka contour menettää (19.6 m / tuki 0.64, 15.7 m / 0.51,
  9.8 m / 0.79, 9.3 m / 0.92; contourin pisin on 9.4 m). Oikea korjaus ei siis
  ole reitityksen kääntäminen vaan histogrammin heikkojen tuotosten karsinta.
  **Nykyinen karsinta ei osu näihin:** ne ovat *jatkuvia mutta tuettomia*
  (`wall_007` tuki 0.17 / jatkuvuus 0.94), ja `prune_unsupported_walls` katsoo
  jatkuvuutta.
  **ANSA — `support_offset is None` EI tarkoita "pintaa ei ole".** Se lasketaan
  vain kun `support < 0.15 TAI continuity < 0.30` (`measure_wall_support`),
  joten näillä viidellä (tuki 0.16–0.21, jatkuvuus 0.38–0.94) sitä ei ollut
  laskettu lainkaan — `None` tarkoitti "ei mitattu". Kun `_nearest_surface`
  ajetaan niille suoraan, kolme on aitoja haamuja (ei pintaa ±1000 mm) mutta
  **kaksi on SIIRTYNEITÄ**: `wall_007` 842 mm, `wall_ext_013` 492 mm. Kynnyksen
  nosto olisi poistanut nekin. Älä lue tästä kentästä puuttumista todisteeksi
  ilman että tarkistat laskettiinko se.
  **Eikä tuen kynnystä voi nostaa:** Rohbaun GT-aito `wall_ext_011` on tuki
  0.21 (GT-puhtaus 0.90), eli se osuu aulan heikkojen 0.16–0.21 väliin. Mikään
  globaali tukikynnys ei erota näitä — tuen taso riippuu keilausgeometriasta,
  ei seinän aitoudesta (Rohbaun aidot 0.21–0.43, aulan aidot 0.17–0.92).

- **ISO E57 luetaan lohkoissa (≥40 M pistettä) — ja se MUUTTAA TULOSTA hieman.**
  `read_scan` varaa koko skannin kerralla, ja iso keilaus on **yksi** skanni,
  joten per-skanni-rajaus ei auta. Mitattu `gargage.e57`: 0.56 GB → 27.8 M
  pistettä, huippu-RSS 2.79 GB (≈5 GB per tiedosto-GB) → **32 GB ≈ 1.6 mrd
  pistettä ≈ 159 GB RSS** eli ei latautuisi lainkaan. Sama libE57-lukija
  palvelee lohkoittain (`libe57.CompressedVectorReader` puskureilla), ja
  `e57_band_chunks` tuottaa **täsmälleen saman pistejoukon** kuin koko luku
  (todennettu: 449 240 = 449 240, järjestetyt taulukot identtiset), huippu
  2.79 → 0.60 GB.
  **MUTTA päästä päähän tulos ei ole identtinen:** voxelointi tapahtuu
  lohkorajoilla ja kerroshistogrammi luetaan desimoituna (`read_e57_z`), joten
  kerrosraja siirtyy senttejä — mitattu gargage.e57: kaista 2.60 → 2.57 m ja
  malli **11 → 9 seinää**. Siksi lohkoluku on portitettu samalla säännöllä kuin
  PLY:llä (≥40 M pistettä): tiedostot jotka latautuvat jo nyt EIVÄT saa uutta
  polkua. Älä laske rajaa "koska se on nopeampi".

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
- **Aukon okkluusiovarjo-testi: MIN yli skannerien, ei MAX.** `_is_occlusion_shadow`
  hylkäsi ennen aukon heti kun YKSI skanneri näki kalusteen aukon kohdalla (max) →
  kalustetussa tilassa jokainen aito aukko katosi (Matterport-aula: 3/3 aukkoa
  hukkui). Aito aukko = JOKIN skanneri näkee sen läpi (matala luku); aito varjo =
  kaikki skannerit tukossa. → hylkää vain jos VÄHITEN peittynytkin skanneri ylittää
  kynnyksen. Grazing-kulmalla (>75° normaalista) katsova skanneri antaa
  keinotekoisen matalan luvun → ohitetaan. Mitattu aulalla: ovi min=71, ikkuna
  min=26, ovi min=0 → 3/3 säilyy; aito kalustevarjo (min~100 k) yhä hylätään.
- **LIIKETILA, mitattu synteettisellä 72×48×7 m myymälällä** (`data/_synth_retail.py`,
  8.2 M pistettä, GT tunnettu). Hyvin: kaikki 9 GT-seinää löytyi, jokainen 24
  seinästä ≤0.4 mm pinnastaan (`_tol_heatmap`), sisäseinien paksuus täsmälleen
  oikein (120/200 mm). Auki:
  1. ~~Lattia-katto-hyllykkö tuottaa valeseinän~~ **KORJATTU (v0.9.3):
     `remove_shelf_front_walls`** — hyllyn etupinta on geometrisesti seinä eikä
     suodatin poista sitä, mutta se on LYHYEHKÖ seinä rinnakkain ja 300–1500 mm
     irti PALJON PIDEMMÄSTÄ perimetriseinästä (jonka edessä se seisoo). Mitattu:
     retail hylly-valeseinät 2→0, GT-kattavuus 9/9 säilyi, asunto/talo no-op.
  3. ~~Pilareita 24/34~~ **KORJATTU: 34/34** (ks. "Pilarin irrallisuus" alla).
  4. Yksipuolisten ulkoseinien paksuus 66–92 mm (todellinen 250) — pinta on oikein,
     paksuutta ei voi mitata.
- **HISTOGRAMMI-DETEKTORI korvaa RANSACin liiketilassa (5.8.2026, uusi
  `wall_histogram.py`).** RANSAC (o3d.segment_plane) oli epädeterministinen
  (OpenMP-säie-tie → sama skanni 17/18/18 seinää eri ajoissa; yksisäie korjaisi
  mutta 6× hitaampi → rikkoo "ei saa hidastu"), hidas (~130 s isossa pilvessä) ja
  sen kallistuneet tasot nappasivat pilarilinjoja (kontaminaatio → yliulottuma).
  Uusi detektori: kierrä pilvi pääsuuntiin (`_dominant_angle`, Σcount²-maksimointi),
  keskikorkeusviipale, histogrammoi x & y → seinä = tiheyspiikki; piikkiparit
  (≤500 mm) = saman seinän kaksi pintaa → PAKSUUS suoraan; jänne dense-runista
  (ei venymää). **Deterministinen, ~130× nopeampi (0.3 s), pilarivapaa
  rakenteellisesti.** Mitattu 48×32 m myymälä AUTO: **9/9 seinää, 13/13 pilaria,
  0 spuriaaliseinää, backroom täydellinen ruudukko** (vs RANSAC 8-9/9, 4-13 pilaria,
  2-5 spuriaali, heittelee) — vision. Kytkentä: pipeline._detect vaihtaa
  `ransac/density` → `histogram` kun `_looks_like_retail` (iso+korkea). VAIN
  suorakulmaisille (Manhattan): asunto/talo voivat olla ei-Manhattan (vino seinä)
  → histogrammi löytää vähemmän (asunto 6 vs contour 9) → ne pitävät CONTOUR:n,
  eivät triggeröi. RANSAC jää fallbackiksi (vinot seinät). `--detector histogram`
  pakottaa.
- **ISO TILA → histogrammi MYÖS ilman "korkeaa" ehtoa; pohja-ala mitataan
  MIEHITYSRUUDUISTA ei percentiilistä (5.8.2026).** Matterport-aula (46 M pistettä,
  9 asemaa yhdessä huoneessa): contour rakensi seinät vain tiheän lattiakontuurin
  ympärille (349 m² skannerihuone) ja koko vasen halli — jonka seinäpinnat näkyvät
  TERÄVINÄ keskikorkeudella mutta lattia on okkluusiovarjossa — jäi mallintamatta
  (13 seinää, 1 tila). Residuaalinäkymä (`data/_navigate.py residual`) paljasti sen:
  vasen halli oli täynnä kattamattomia (punaisia) aitoja seinälinjoja. **Tämä
  KUMOSI aiemman "lasin takana, jätä pois" -päätelmän** — läpi lasin näkyvä tila on
  HARVA/kohinainen, aula-halli oli tiheä ja teräväviivainen = aito keilattu tila.
  Kaksi ansaa: (1) `_looks_like_retail`-korkeus (p1–p99 z) oli aulalla vain 3.86 m
  (harva katto) → ei "korkea"; (2) sen pinta-ala on tiheyspainotettu x/y-percentiili
  → skannerihuone dominoi → 270 m² < 600. Molemmat aliarvioivat. Ratkaisu:
  `_occupancy_area_m2` (miehitetyt 1 m xy-ruudut, TIHEYSRIIPPUMATON: harvakin
  kaukoseinä lasketaan) ja `_detect` valitsee histogrammin kun **miehitysala ≥400 m²
  TAI `_looks_like_retail`** — myös contour-OLETUKSESTA (aula 825 m², asunto 31,
  talo 54 → vain iso tila triggeröi). Mitattu: aula 13→11 seinää mutta OIKEAT
  (koko rakennusvaippa, 1→6 tilaa; residuaali vision). Gauntlet vihreä: retail-synt
  9/9 seinää + 34/34 pilaria + 0 hyllyvaleseinää ennallaan; asunto/talo identtiset
  (pieni ala + matala → detektori pysyy contourissa). Histogrammi contouria
  nopeampi → ei hidastu.
- **ISO MYYMÄLÄ, mitattu synteettisellä 96×64×8 m myymälällä** (`data/_synth_retail.py
  --sx 96000 --sy 64000 --height 8000`, 57 M pistettä, GT tunnettu). ÄLÄ aja
  `python -m scan2bim <ply>` — se avaa GUI:n; oikea CLI on `scan2bim convert`
  (tai `-m scan2bim.cli`). Ajo ~13 min. Löydökset:
  1. ~~Seinän akseli venyi 9–31 m rakennuksen ULKOPUOLELLE tyhjän lattian yli~~
     **KORJATTU (cb224ba): `_trim_endpoints` sallii >300 mm leikkauksen kun kaista
     on kiistatta aito (span ≥2.5 m + ≥300 pintapistettä).** Seinät 5/9→7/9,
     pilarit 51/65→65/65, ei ulkopuolisia seiniä (vision).
  2. AUKI: perimetrin ulkopinta erotellaan omaksi seinäksi (`wall_ext_*`, ~414 mm
     irti aitosta akselista) isoilla ulkoseinillä → tuplaseinä.
  3. AUKI: lattia-katto-hylly AIVAN seinää vasten (30–50 mm irti) jää valeseinäksi
     — `remove_shelf_front_walls` alaraja on 300 mm, ei nappaa <300 mm skiniä.
  4. ~~Takahuoneen väliseinät jäivät löytymättä~~ **KORJATTU (recall 6/9→9/9):
     RANSAC-confidence oli koko-suhteinen (`inliers/(total×0.05)`) → isossa
     myymälässä aito 12 m sisäseinä = murto-osa pilvestä → conf ~0.01 → filtteri
     pudotti. Lisätty skaalariippumaton PEITTO (`_dense_segment`/`_axis_coverage`,
     wall_ransac.py): `confidence=max(koko_conf, peitto)`, ja `filter_structural_walls`
     säilyttää seinän jos peitto ≥0.5. Peitto mitataan tiheintä yhtäjaksoista
     jännettä pitkin (ovet sillataan ≤1.6 m; jänne ≥2 m ettei pilaririvi kelpaa).
     Retail AUTO: 9/9 seinää, hyllyt 0, 7 tilaa (vision). Asunto/talo käyttävät
     CONTOUR-detektoria → muutos ei koske niitä (9/3, 9/2 ennallaan).
  5. ~~Rescatut backroom-pystyt yliulottuvat ~8 m myyntitilaan~~ **OSIN KORJATTU
     (2/3): `_trim_endpoints` mittasi päätepisteen KOKO korkeudelta → seinän
     x-kaistan LATTIA/KATTOLAATTA (pisteitä joka y:llä) venytti seinän tilan
     syvyyden yli. Trim käyttää nyt KESKIKORKEUTTA (0.25–0.75 H) → vain seinäpinta,
     ei laattaa.** Mitattu: 3:sta backroom-pystystä 2 leikkautuu oikein y≈12160:een
     (ennen kaikki y≈22000). Asunto/talo ennallaan (9/3, 9/2), 122 testiä.
     JÄLJELLÄ: pilarilinjan VIERESSÄ (≤~350 mm) oleva seinä yliulottuu yhä
     (pilari on pystyrakenne → näkyy keskikorkeudellakin); aisle-hyllyt (pystyt
     gondolit) jäävät valeseiniksi OFF-moodissa (auto/suodatin osin hoitaa).
     Dense-axis-fit kokeiltu mutta hylätty (RANSAC-kohina, pilarit 3–13).
- **Liiketilojen hyllyt** (lattia-katto) läpäisevät geometrisen pystymaskin →
  semanttinen suodatin tarvitaan. **KYTKETTY (4.8.2026): `semantic_filter_mode="auto"`
  on nyt OLETUS.** `_looks_like_retail(cloud)` (pipeline.py) kytkee PointNet-
  suodattimen VAIN big-box-liiketilaan (pohja ≥600 m² JA korkeus ≥4.5 m — lattia-
  katto-hyllyt vaativat korkean tilan). Mitattu: retail hylly-valeseinät 2→0
  (koko-mittainen hylly = geometrisesti seinä, len_ratio-erotin ei pysty; suodatin
  pystyy), pilarit 20/20, asunto/talo EIVÄT triggeröi (9/3 ja 9/2 muuttumattomat,
  ei hidastu). SYY vain-retail-ehdolle: suodatin REGRESSOI asuintaloa (talo 9→8
  seinää, 2→1 huone, poistaa aidon seinän+huoneen — vision-varmistettu). CLI:
  `--semantic-filter auto|off|pointnet`. **`pointnet-retail` on edelleen ALIAS
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

**Testidata — MIKÄÄN EI OLE GITISSÄ** (`.gitignore`: `data/*.ply`, `*.npy`,
`data/_rohbau/`, `data/_3dses/`), eikä release-asseteissa. Jokainen kone lataa
omansa; `data/_paths.py` etsii ne `~/Downloads`:sta tai `SCAN2BIM_DOWNLOADS`:sta.
Kirjaa tähän jokainen uusi setti + sen LÄHDE, muuten kukaan ei tiedä mistä sen saa.

| data | sijainti | lähde / lisenssi |
|---|---|---|
| Rohbau3D site_07 (kalustamaton runko, **per-piste-GT**) | `data/_rohbau/` | open-data.unibw.de doi:10.60776/ZWJFI4, **MIT** — paras puhdas tarkkuustesti, turvallinen myös myyntimateriaaliin |
| 3DSES (TLS npy Nx7 + CAD .obj) | `data/_3dses/` | Zenodo 13323342, **CC BY-SA 4.0** → ShareAlike-riski, ei myyntikuviin |
| synteettinen myymälä/kauppakeskus + `.gt.json` | `data/_retail_{s,l}.ply` | oma (`data/_synth_retail.py`), lisenssivapaa |
| `gargage.e57` (27.8 M, 1 skanni; images2D on mutta 0 kelvollista asemaa) | `~/Downloads` | oma/asiakkaan — omistajuus selvittämättä |
| `parking-lot-updated.e57` (285 kuvaa, 1 asema) | `~/Downloads` | oma/asiakkaan — **ainoa paikallinen kuvallinen E57**, kuvaohjatun aukkodetektion testi |
| `aligned_low_{apartment,bedroom}`, `raw_scans_apartment` | `~/Downloads` | oma/asiakkaan — omistajuus selvittämättä |
| **Matterport-aula** (9 asemaa, 58.3 M pistettä, 54 skybox-kuvaa) | `~/Downloads/matterport_lobby.e57` | **Matterportin JULKINEN näytetiedosto**, lataa uudelleen: `https://static.matterport.com/misc/UoqjwziqrZs-Aon_Lobby.e57` (1.15 GB, "Aon Lobby"). Ainoa data jossa on sekä kuvat ETTÄ yli 40 M pistettä → testaa kuvaohjatun aukkodetektion JA e57-lohkoluvun |

## Työskentelyn konventiot

- **Suomi** chatissa ja dokumenteissa, **englanti** commit-viesteissä ja koodikommenteissa.
- **Suora push masteriin** sallittu (henkilökohtainen repo, ei PR-flowta).
- Commit-trailer AI-commiteissa: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Versiopumppi** koskettaa: `src/scan2bim/_version.py`, `build/version_info.py`
  (4 kenttää). `v*.*.*`-release julkaistaan **`Mcrauli/scan2bim-web`**-repoon
  → itsepäivitys hakee sen. **Kuusi assettia, ei viittä:**
  `scan2bim-<v>.zip` + `.sha256` (itsepäivityksen payload),
  `scan2bim-Setup-<v>.exe` + `.sha256` (uusasennus) ja
  **`scan2bim-Setup.exe` + `.sha256` (VERSIOIMATON)** — nettisivun
  `index.html` osoittaa kiinteään nimeen `releases/latest/download/scan2bim-Setup.exe`,
  ja kun se puuttui v0.9.17:stä ja v0.9.18:sta, sivun latausnappi oli 404
  kymmenen päivää. `scripts/build_installer.ps1` tekee kopion automaattisesti;
  tarkista julkaisun jälkeen `curl -sL -r 0-100 -o /dev/null -w "%{http_code}"`.
  Julkaisuketju: `$env:ISCC = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"`
  → `scripts\build_installer.ps1` → `gh release create`.
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

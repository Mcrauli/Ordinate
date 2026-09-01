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

**Uusi, tuntematon skanni: aja `scan2bim inspect <tiedosto>` ENSIN.** Se lukee
ne oletukset jotka putki tekee — mittakaava, lattia- ja kattotaso, kerrosjako,
pisteväli — ja varoittaa siitä mikä oikeasti kaataa ajon: liian pieni laajuus
(mittakaava väärin), iso z-laajuus (monikerros tai rekisteröintivirhe), liian
harva skanni ohuille seinille. Se **ei lataa tiedostoa muistiin**: E57 luetaan
skanni kerrallaan harventaen, joten se toimii myös sillä 32 GB:n tiedostolla
jota ei voi ajaa. Tiheys mitataan yhtenäisestä lohkosta — harvennetusta
näytteestä se olisi 50 % liian suuri ja varoittaisi turhaan.

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

**Aloita tästä:** `.venv/Scripts/python.exe data/_qa_all.py` tulostaa kaikki
mittarit yhtenä taulukkona (aineisto × elementtityyppi × kattavuus/tarkkuus).
Se EI aja putkea, joten se merkitsee `!`-etuliitteellä jokaisen mallin joka on
vanhempi kuin uusin `src/`-muutos — sellaisen luvut on ajettu eri koodilla
eivätkä ne ole todiste nykyisestä puusta. Aja putki uudelleen ennen kuin nojaat
niihin.

**Kattavuus mitataan INSTANSSEINA, ei pisteinä.** Pistekattavuus on painotettu
elementin koolla, joten yksi iso perimetriseinä peittää monta puuttuvaa pientä:
Rohbaussa seinien pistekattavuus on 0.75–0.89 mutta instanssikattavuus
0.30–0.49. Sama harha piilotti palkkien 0/77:n. Jokaisella elementtityypillä on
oma `_*_qa.py` joka laskee instanssit.


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
| `data/_beam_qa.py` | **Palkkien GT-vertailu**: mallin palkkilaatikoiden GT-luokkajakauma JA montako GT:n palkki-instanssia (`instance.npy`) löytyi. Seinäpuolen `_rohbau_qa.py`:n vastine — ilman tätä palkkidetektorin kynnyksiä ei ollut mitattu mitään vasten |
| `data/_beam_synth_qa.py` | **Palkit synteettistä GT:tä vasten**: kattavuus GT-palkin akselipituudesta ja tarkkuus mallin palkkipituudesta. Rohbaun palkit ovat 2.5–5.5 m jättiläisiä, joten tavallisen kokoluokan (300 mm) totuus on vain täällä |
| `data/_soffit_probe.py`, `data/_soffit_sweep.py` | **Alapintalaikkujen mitat GT-luokan rinnalla**: portit valitaan mitatusta välistä. `_beam_probe.py` näyttää mihin porttiin kukin klusteri kaatuu |
| `data/_beam_run.py` | Ajaa **pelkän palkkidetektion** valmiiseen malliin (`model.beams.json`) — porttien säätö ei vaadi putkiajoa |
| `data/_wall_inst_qa.py` | **Seinät instansseina, ei pisteinä**: montako GT-seinäinstanssia on mallissa. Pistekattavuus 0.81–0.89 piilottaa sen että puolet seinistä puuttuu |
| `data/_opening_view.py`, `data/_opening_probe.py`, `data/_opening_run.py` | **Aukot kuvana ja syittäin**: erottaa 'aukko seinällä jota ei ole mallinnettu' 'aukosta jota detektori ei löydä', ja katsoo näkyykö reikä pilvessä lainkaan |
| `data/_opening_qa.py` | **Aukot GT:tä vasten** (Rohbau luokat 7/12/13/14): montako GT-aukkoinstanssia osuu mallin aukkoon ja päinvastoin |
| `data/_qa_all.py` | **Kaikki mittarit yhtenä taulukkona**: aineisto × elementtityyppi × (kattavuus, tarkkuus). Ei aja putkea — näyttää mallin IÄN, jotta vanhentunut tulos ei mene uutena luvusta läpi (paljasti heti 2 vrk vanhat liiketilamallit) |
| `data/_column_qa.py`, `data/_col_gate_gt.py`, `data/_column_run.py` | **Pilarit GT:tä vasten** ja mikä portti hylkää minkäkin GT-pilarin |
| `data/_second_face_probe.py` | **Keksiikö katvepintahaku seiniä**: ajaa aineistot joilla ei ole GT:tä ja tulostaa löydetyt katveseinät tuki/jatkuvuus-lukuineen |
| `data/_shelf_gt_probe.py` | Mitä `remove_shelf_front_walls` oikeasti poistaa — poistettujen GT-luokkajakauma Rohbaussa |
| `data/_cont_rule_probe.py` | Vertaa jatkuvuussääntöjä (kiinteä 5 / ≥1 / suhteellinen) eri tiheyksillä ja tulostaa erottelun aito−palkki — tällä valittiin suhteellinen sääntö |
| `data/_ctrl_snapgate.py` | Kontrolliajo: napsautusportti vanhalla (`support == 0`) vs nykyisellä ehdolla, seinien akselit ja GT-luvut rinnakkain — tällä eristettiin kaksi regressiota |
| `data/_lobby_ab.py` | Aulan A/B: auto-reititys vs pakotettu contour, kuva + mitatut tuki/jatkuvuus-luvut. `--plot-only` piirtää uudelleen ajamatta putkea |
| `data/_lobby_cov.py` | Sama A/B kahdesta suunnasta **ilman GT:tä**: tuki (tarkkuuden suunta) ja kaistan lunastettu osuus (kattavuuden suunta), nimittäjä sama molemmille |
| `data/_wall_view.py` | **Liputettu seinä kuvina**: XY vyötäröltä, poikkileikkaus, mallin pinnalla olevat pisteet. Erottaa HAAMUN (ei mitään) VÄÄRÄSSÄ PAIKASSA olevasta (pinta on, mutta sivussa) — pelkkä `support`-luku ei kerro kumpi |
| `data/_img_openings_qa.py` | Kuvaohjattu aukkodetektio oikealla kuvallisella E57:llä; vertaa vanhaan moduuliin samoilla seinillä+pilvellä |
| `data/_split_evidence_probe.py` | **Mikä todiste pitää seinän kasassa**: sama sarake mitattuna nykyisellä (mikä tahansa piste) ja seinämäisellä (pystynormaali + jatkuvuus) todisteella, aukko- ja todistejaksojen pituudet rinnakkain |
| `data/_sem_cache.py` | Ajaa PointNetin kerran ja tallentaa luokat levylle — semanttinen koe maksaa sen jälkeen sekunteja eikä 8 min |
| `data/_prune_sweep.py` | Semanttisen karsinnan kynnyssweep valmiille mallille ILMAN putkiajoa (kattavuus + tarkkuus samalla määritelmällä kuin `_wall_coverage_nogt`) |
| `data/_chain_probe.py` | **Mikä ketjun vaihe kasvattaa seinät**: seinämäärän ja pituuden muutos vaiheittain koko putkiajosta |
| `data/_snap_ablation.py` | Nurkkajatko pois → paljonko mallia jää ja mitä se maksaa kattavuudessa |
| `data/_normals_seg_ab.py` | normals-detektorin segmentointisääntöjen A/B (pisteiden välimatka vs sarakekohtainen peitto) |
| `data/_gt_export.py`, `data/_gt_import.py` | **Ground truth ilman valmista GT:tä**: vie asema CloudCompareen labeloitavaksi ja lue luokkatiedostot takaisin Rohbau-muotoon (`coord.npy` + `class.npy`), jolloin kaikki GT-mittarit toimivat asiakaskohteella |
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

- **PAKSUUS ON KELLARISSA MITATUSTI VÄÄRIN — mutta "vastakkainen pinta" ei ole
  korjaus (mitattu ja KUMOTTU).** `_thickness_lock_wall` valitsee seinän toiseksi
  pinnaksi toiseksi vahvimman piikin 50–400 mm etäisyydeltä riippumatta siitä
  kummalla puolella akselia se on. Piikkiparikoetin (vahvin piikki + vahvin
  piikki TOISELTA puolelta) antaa asunnolle 150 mm kun malli sanoo 154 ja
  Rohbaulle 112 kun malli sanoo 120 — eli koetin ei valehtele siellä missä malli
  on oikeassa — mutta **kellarissa malli sanoo 66 mm ja pinnat ovat 225 mm
  päässä**, mediaanivirhe +109 mm ja 30/57 seinää yli 100 mm alakanttiin.
  Se ei ole kosmeettista: 66 mm paksuudella mittauskaista on ±33 mm akselista
  eli SEINÄN SISÄLLÄ, joten tuki, kate ja kontrasti mittaavat tyhjää.
  **Korjausyritys "suosi vastakkaisen puolen piikkiä" kumoutui:** kellari
  paranee (kattavuus 0.188 → 0.205) ja asunto paranee selvästi
  (0.681 → **0.725**), mutta Rohbau scene_07000 menettää GT-kattavuutta
  0.886 → **0.843** ja synteettinen 0.688 → **0.635**. Syy on mitattu per seinä:
  Rohbaun `wall_009` paksuuntuu 150 → **272 mm** ja nielaisee `wall_008`:n
  (ne ovat saman rakenteen kaksi pintaa), synteettisen `wall_010` 50 → 66 mm.
  **Kellarissa vahvin ehdokas on väärä (putki) ja vastakkainen oikea; Rohbaussa
  täsmälleen päinvastoin** — erottelua ei ole. Myös jatkuvuus kumoutui: kellarin
  ehdokaspiikeillä on kate 1.00 joka ikisellä. Paksuus on siis yhä auki, ja
  `qa/reliability.py` RAPORTOI sen (kellari −84 mm) sen sijaan että arvaisi.
- **PUTKI EI TIENNYT OLEVANSA EKSYKSISSÄ — nyt se kertoo sen.**
  Kellari tuotti 427 seinää joista valtaosa oli valeseiniä, eikä yksikään putken
  oma luku varoittanut: `confidence` on kokoproxy, `support` ja `continuity`
  mittaavat tasoa joka riippuu skannista, ja TARKISTA-lista jäi lyhyeksi. Vika
  löytyi vasta kuvista. `core/qa/reliability.py` laskee joka ajosta kolme
  SUHDELUKUA ja kirjoittaa ne diagnostiikkaan:
  | signaali | asunto | kellari (ennen korjauksia) |
  |---|---|---|
  | kontrasti ympäristöön, mediaani | 14.15 | 1.00 |
  | seiniä oman pintansa päällä | 100 % | 27 % |
  | paksuusero pinnoista mitattuun | −14 mm | −109 mm |
  Maksaa 5 s (jakaa seinämäisten pisteiden laskennan kontrastiportin kanssa).
  **Se ei korjaa mitään — se kertoo mitä ei kannata uskoa**, jottei seuraava
  tuntematon skanni jää kiinni siitä katsooko joku kuvia.
- **MATRIISI EI TESTANNUT SITÄ MITÄ SOVELLUS TEKEE — ja se piilotti ison bugin.**
  `data/_run_one.py` pakottaa `semantic_filter_mode="pointnet"`, mutta tuotannon
  oletus on `auto`, joka kytki suodattimen päälle vain `_looks_like_retail`illa
  (600 m² **JA** 4.5 m). Koulun kellari on 7137 m² mutta p1–p99-korkeudeltaan
  2.84 m, joten **sovellus ei ajanut suodatinta lainkaan** — eikä siis myöskään
  semanttista karsintaa, joka poistaa siitä mallista 119 seinää. Kaikki mitatut
  kellariparannukset olivat siis olemassa vain matriisissa.
  Korjaus: `auto` kytkee suodattimen myös pelkän ALAN perusteella
  (`_FILTER_MIN_AREA_M2` 600 m²). Krääsä skaalaa pinta-alan mukaan eikä
  korkeuden: 7000 m² talotekniikkakellarissa on enemmän putkea kuin 600 m²
  myymälässä. Asunto (82 m²) ja talo (54 m²) — juuri ne kaksi joita suodatin
  regressoi — jäävät alarajan alle. Todennettu: kellarin malli `auto`-tilassa on
  BITILLEEN sama kuin pakotetulla `pointnet`illa (110 seinää, sama hash).
  **Yleistys: kun QA-ajo käyttää eri asetuksia kuin tuotanto, se mittaa eri
  ohjelmaa.** Tarkista jokaisesta `data/_run_*.py`:stä että konfiguraatio
  vastaa sitä mitä käyttäjä ajaa — tai mittaa molemmat.
- **ONKO SEINÄ PIIRRETTY SUUNTAAN JOSSA ON PINTAA?** Mitattu koulun kellarilla:
  **58 % mallin seinäpituudesta (238 m / 411 m) kulkee suuntaan jota detektori
  ei löytänyt lainkaan**, ja kaksi parhaiten tuettua suuntaa (21° ja 111°,
  17 % ja 15 % normaalimassasta) oli mallinnettu 2.9 m ja 0.0 m. Ne 238 m ovat
  juuri niitä pitkiä vinoja linjoja jotka läpäisevät kaikki muut portit — ne
  ovat tasomaisia jossain ja koskettavat pintaa siellä täällä. Suunnat eivät
  ole detektorin keksimiä vaan KETJUN: suoristus, nurkkasnäppäys, perimetri ja
  kollineaarinen sulautus siirtävät akseleita.
  Mittari on pilven oma normaalihistogrammi, seinän suunta siitä luettuna
  suhteessa maksimiin (`semantics/direction_prune.py`):
  | aineisto | min | mediaani | alle 0.30 |
  |---|---|---|---|
  | liiketila | 0.86 | 0.86 | 0 m |
  | asunto | 0.54 | 1.00 | 0 m |
  | Rohbau 07000 | 0.00 | 0.78 | 3 m / 226 |
  | **kellari** | 0.03 | **0.14** | **208 m / 358** |
  Kynnys **0.20** on mitattu yläraja: 0.30 romahduttaa scene_07002:n
  GT-kattavuuden 0.863 → **0.524**. 0.20:llä matriisi on bitilleen ennallaan
  kaikilla yhdellätoista muulla aineistolla ja kellari menee 101 → 66 seinää,
  tarkkuus 0.207 → **0.249** — ja kuvassa jokainen jäljelle jäänyt seinä on
  harmaan pinnan päällä.
  **TÄMÄ EI OLE `drop_skew` UUDELLEEN.** Se pudotti seinän joka poikkesi yli
  22° PERHESUUNNASTA eli geometrisesta Manhattan-priorista, ja kaatui siihen
  että kellarissa on kuusi aitoa suuntaa 20° välein. Tämä lukee saman pilven
  mitatun jakauman eikä oleta suuntien määrää: jos rakennuksessa on kuusi
  suuntaa, kaikki kuusi näkyvät histogrammissa ja kaikki kuusi kelpaavat
  (testattu `tests/test_direction_prune.py`).
- **KUMOTTU: seinän pilkkominen tasomaisuuden mukaan.** Ajatus oli että portit
  osaavat vain poistaa kokonaisia seiniä, joten pitkä vino valeseinä pitäisi
  pilkkoa niistä kohdista joissa kaista ei ole taso. Mitattu (pilkkominen
  valmiiseen malliin, katkaisu kolmesta peräkkäisestä ei-tasoisesta
  sarakkeesta): GT-kattavuus laskee **jokaisella** Rohbau-scenellä
  (0.915→0.909, 0.903→0.890, 0.863→0.854, 0.849→0.843, 0.759→0.736) ja ostaa
  vain 0.000–0.003 tarkkuutta. Kellarikin menettää enemmän kuin voittaa
  (0.199/0.192 → 0.175/0.221). Oikea vastaus samaan ongelmaan oli SUUNTA, ei
  pilkkominen.
- **JÄÄNNÖSSEINÄHAKU KYTKETTY TAKAISIN (30.8.2026) — sama moduuli, eri ketju.**
  Se kytkettiin pois 18.8. koska ehdokkaista vain 8/15 oli GT-seiniä ja
  scene_07000:n tarkkuus romahti 0.924 → 0.515: ehdokas ei pystynyt
  todistamaan itseään eikä yksikään silloin kokeiltu erottelija pystynyt
  siihen. Sen jälkeen ketjuun on tullut kolme MITATTUA porttia — semanttinen
  enemmistöääni, kontrasti ympäristöön ja kaistan tasomaisuus — ja kellarin
  jäännöksestä mitattuna kaikki 19 ehdokasta (75 m) ovat tasomaisia 0.75–1.00,
  eli portit osaavat nyt tuomita juuri nämä. Sama moduuli samoilla kynnyksillä:
  | aineisto | GT-kattavuus | GT-tarkkuus | GT-vapaa kattavuus |
  |---|---|---|---|
  | scene_07000 | 0.886 → **0.915** | 0.914 → 0.898 | 0.959 |
  | scene_07001 | 0.863 → **0.903** | 0.957 → 0.945 | 0.852 → 0.854 |
  | scene_07002 | 0.859 → **0.863** | 0.964 → 0.956 | 0.894 → 0.896 |
  | scene_07003 | 0.824 → **0.849** | 0.923 → 0.921 | 0.533 → **0.600** |
  | scene_07004 | 0.755 → **0.759** | 0.927 → 0.925 | 0.598 → **0.640** |
  | synteettinen | – | – | 0.688 → **0.785** |
  | liiketila-L | – | – | 0.620 → **0.695** |
  | kellari | – | – | 0.177 → **0.191** (tarkkuus 0.202 → 0.207) |
  Kattavuus nousee KAIKILLA viidellä Rohbau-scenellä ja hinta on 0.002–0.016
  GT-tarkkuutta — sama vaihtokurssi jonka palkkien kiinnitysportti sai
  (23 aitoa palkkia 0.016 tarkkuudesta). Asunto, liiketila-S, test_room ja
  3DSES eivät menetä kattavuutta.
  **YLEISTYS: kumottu sääntö kannattaa mitata uudelleen kun ketjuun on tullut
  uusi todiste.** Se ei ollut väärä idea vaan liian aikainen — vika oli siinä
  ettei mikään myöhempi vaihe osannut hylätä huonoa ehdokasta.
- **ONKO KAISTASSA TASO? Tämä on ainoa erottelija joka kesti kaikki yhdeksän
  aineistoa.** Muut portit kysyvät onko seinän kohdalla PINTAA; putkikellarissa
  on aina. Aito seinäpinta on TASO — kaistan kohtisuora hajonta on millejä —
  kun putki ja kanava täyttävät kaistan tasaisesti. Hajonta on mitta pinnasta
  itsestään: se ei riipu keilaustiheydestä, huonekorkeudesta eikä siitä
  näkyykö seinästä kolmannes vai kaikki, ja juuri siihen kaatuivat seinämäinen
  kate, komponenttikoko ja jatkuvuus. Mitattu kaistan mediaanihajonta:
  | aineisto | MAD | tasomaisia sarakkeita |
  |---|---|---|
  | liiketila | 2.1 mm | 1.00 |
  | asunto | 4.2 mm | 0.94 |
  | Rohbau (5 sceneä) | 2.8–6.1 mm | 0.88–0.94 |
  | synteettinen | 14.6 mm | 0.57 |
  | **koulun kellari** | **28.7 mm** | **0.25** |
  `semantics/flatness_prune.py`, kynnys 0.20. Matriisi: Rohbau 07003:n
  GT-tarkkuus **0.912 → 0.923**, 3DSES **0.582 → 0.664**, kaikki muut
  bitilleen ennallaan, kellari 101 → 93 seinää ja tarkkuus 0.194 → 0.202.
  **KAKSI ANSAA, molemmat mitattuja:**
  1. *Kaista ei saa ylettyä seinän keskilinjan yli.* 66 mm seinällä ±120 mm
     nielaisee vastapinnan ja hajonta on aina iso riippumatta siitä onko pinta
     taso — synteettisen aito `wall_001` sai 0.14 ja putosi (kattavuus
     0.688 → 0.627). Kaista on `min(120, paksuus/2)`; korjauksen jälkeen sama
     seinä saa 0.86 ja kaikki 13 säilyvät.
  2. *Kynnystä EI saa tehdä suhteelliseksi.* Kokeiltu "alle 3 × mallin oman
     p10-hajonnan": p10 on 1–2.5 mm joka aineistossa (yksi hyvin keilattu
     sarake löytyy aina), joten raja 6 mm romahduttaa asunnon mediaanin
     0.94 → 0.59 ja synteettisen 0.57 → 0.14. 20 mm on fysikaalinen raja:
     sitä paksumpi hajonta ei ole rakennettu taso.
- **TASO RIIPPUU SKANNISTA, SUHDE EI — mittaa seinää sen omaa ympäristöä
  vasten.** Jokainen kaatunut erottelija (tuki, jatkuvuus, kate, komponenttikoko,
  liittyvyys, seinämäinen kate) mittaa TASOA, ja sama luku tarkoittaa eri asiaa
  1.8 m kellarissa ja 10 m hallissa. Toimiva mitta on **kontrasti**: pystypintaa
  seinän omalla pinnalla vs. sama mitta 0.75–1.25 m sivussa, samalta pituudelta.
  | aineisto | min | mediaani |
  |---|---|---|
  | asunto | 1.87 | 2.40 |
  | liiketila | 1.95 | 43.5 |
  | Rohbau (5 sceneä) | 1.00 | 1.9–2.1 |
  | kellari | **0.01** | **1.00** |
  Kellarin tyypillisen mallinnetun seinän kohdalla on siis täsmälleen yhtä paljon
  pystypintaa kuin metrin sivussa — se ei ole seinä, se on kohta putkimetsässä.
  **KAKSI ANSAA, molemmat mitattuja:**
  1. *Kontrolli on mitattava PINNASTA ULOSPÄIN.* `half - c` osuu seinän sisään,
     jossa ei ole koskaan pintaa, ja painaa mediaanin nollaan → kontrasti
     kaksinkertaistuu keinotekoisesti. Oma testini meni ensin läpi väärästä
     syystä juuri tällä.
  2. *0/0 EI ole todiste.* Rohbaun 10 m hallissa seinämäisyys vaatii pystypintaa
     yli puolet kaistan korkeudesta ja lattialta keilatusta seinästä näkyy
     kolmannes, joten aidon seinän molemmilla puolilla on nolla pistettä ja
     kontrasti on 1.00 pelkästä nollasta. Ilman sokeusehtoa portti poistaisi
     scene_07004:n aidon `wall_001`:n (GT-kattavuus −0.017). Ehto: tuomitse vain
     jos seinän ±3 m ympäristössä on pintaa ≥10 % mallin OMASTA mediaanista —
     Rohbaun tyhjien ympäristö on 0 pistettä/m, kellarin 31–64 kun mediaani 143.
  **Kontrasti EI toimi detektorin sisällä.** Tasokohtaisena (koko rakennuksen
  läpi kulkeva taso) se laimenee: 302 → 298 seinää. Segmenttikohtaisena mutta
  suuntasuodatetuista pisteistä laskettuna se on aina korkea, koska metrin
  sivussa ei ole samaan suuntaan osoittavia normaaleja: 302 → 302. Vasta
  KAIKISTA seinämäisistä pisteistä laskettuna se puree (302 → 268), ja
  lopullinen erottelu syntyy vasta ketjun jälkeen — kellarin alle 1.0 jäävistä
  seinistä valtaosa syntyy ketjussa, ei detektiossa.
- **PUTKIKELLARISSA "ONKO KAISTASSA PISTEITÄ" ON AINA TOSI — SE MITTAA
  RAKENNUSTA, EI SEINÄÄ.** `split_walls_at_gaps` katkoo seinän sarakkeesta
  jossa on alle 4 pistettä 150 mm kaistassa. Mitattu koulun kellarilla
  (`data/_split_evidence_probe.py`, 396 seinää): sarakekate on **p10 1.00,
  mediaani 1.00** — sääntö ei laukea kertaakaan, koska matalassa
  talotekniikkakellarissa jokaisen linjan varrella on putki, kanava tai
  kaapeli. Sama seinäjoukko seinämäisellä todisteella (pystynormaali +
  pystyjatkuvuus) mitattuna: mediaani **0.00**, ja 284 seinää 396:sta on
  "täynnä" vanhalla ja alle 0.30 uudella.
  **KUMOTTU KORJAUS — seinämäistä todistetta EI voi vaihtaa tilalle.** Rohbaun
  aidot seinät (GT-tarkkuus 0.91–0.96) käyttäytyvät samalla mittarilla
  täsmälleen kuten kellarin ristikko:
  | | kellari | 07000 | 07003 | asunto |
  |---|---|---|---|---|
  | seinämäinen kate, med | 0.00 | 0.25 | 0.14 | 1.00 |
  | pisin tyhjä jakso, med | 3.0 m | 2.8 m | 2.5 m | 0.0 m |
  | osuus ≥2 m aukoissa | 0.84 | 0.75 | 0.73 | 0.00 |
  Syy: seinämäisyys vaatii pystypintaa yli puolet KAISTAN korkeudesta, ja 10 m
  hallissa lattialta keilatusta seinästä näkyy kolmannes. Sama koskee
  komponenttikokoa: Rohbau 07000:n seinämäisistä pisteistä **93 % on alle 4 m
  komponenteissa**, eli "lyhyt pala = pilari" -sääntökään ei erota. Mittarin
  ABSOLUUTTINEN taso ei siirry kohteesta toiseen (`qa/coverage.py`:n docstring
  sanoo tämän) — älä rakenne sen varaan karsintasääntöä.
- **`snap_corners` KASVATTAA MALLIA ENEMMÄN KUIN KOKO MUU KETJU KARSII — mutta
  kokonaisbudjetti ei ole korjaus (mitattu ja KUMOTTU).** Ketju ajaa
  `snap_corners`:n kahdeksan kertaa ja jokainen kutsu saa jatkaa pään 1300 mm
  risteykseen, joten raja on per KUTSU eikä per seinä. Mitattu kellarilla
  (`data/_chain_probe.py`): **snap_corners +2009 m**, kaikki muut vaiheet
  yhteensä −270 m; detektorin 302 pätkästä (keskipituus 3.5 m, neljä yli 8 m)
  tuli 333 seinää joista **58 yli 8 m**. Ablaatio (`data/_snap_ablation.py`,
  jatko 1300 → 0 mm): malli 742 → **363 m**, kattavuus 0.281 → 0.269,
  tarkkuus 0.125 → **0.174** — jatko ei siis osta kattavuutta.
  **Silti per-seinä-budjetti hylättiin:** (1) se regressoi muut aineistot
  (synteettinen kattavuus 0.692 → **0.600**, Rohbau 07002 GT-tarkkuus
  0.964 → **0.860**, 07003 GT-kattavuus 0.824 → 0.804), koska ketjun myöhemmät
  vaiheet siirtävät seiniä ja nurkka on suljettava uudelleen — mitattu aito
  kasvu on asunnossa **max 4.7 m** ja synteettisessä 1.7 m, eli aidon ja
  patologisen välillä ei ole rakoa; ja (2) se ei tuonut kellarille mitään
  karsintakynnyksen päälle (160 vs 176 seinää, tarkkuus 0.150 vs 0.149).
  Trimmauksen hyvittäminen budjettiin (netto) ei muuttanut tulosta bitilläkään.
  Kasvu on siis oikea havainto mutta väärä korjauskohta.
- **VINO SEINÄ EI OLE TODISTE VIRHEESTÄ — `drop_skew` oli päällekkäinen suoja.**
  `regularize_orthogonal(drop_skew=True)` pudotti jokaisen seinän joka jäi yli
  22° päähän perhesuunnasta, perusteena "asunto on Manhattan-world". Evidenssin
  mittaa kuitenkin `prune_unsupported_walls`, joka ajetaan joka tapauksessa —
  tämä tuomitsi geometrian perusteella. Mitattu koulun kellarilla (normaali-
  detektorin löytämät suunnat 1°, 21°, 41°, 91°, 111°, 131° eli kuusi suuntaa
  20° välein):
  | asetus | seiniä | kattavuus |
  |---|---|---|
  | tol 22, drop=True (vanha) | 314 | 0.253 |
  | tol 22, drop=False | 374 | **0.361** |
  Koko putken läpi kellari nousi **0.108 → 0.310**, muut yksitoista aineistoa
  ennallaan. HUOM: 22° toleranssi on niin löysä että se nielaisee 20° välein
  olevat suunnat — pilvestä mitattu "Manhattan-osuus" oli kellarissakin 0.871,
  eli se EI paljasta tätä. Vika oli pudotuksessa, ei kääntämisessä.
- **DETEKTORIVALINTA MITTAA RAAKAA TULOSTA — älä lisää siihen käsittelyä.**
  Lisäsin valintaan karsinnan ja perimetrin, jotta ehdokkaita verrattaisiin
  "valmiimpina". Se muutti contourin ja histogrammin keskinäistä järjestystä ja
  vei Rohbau scene_07003:n GT-kattavuuden **0.807 → 0.691**, vaikka GT-vapaa
  luku NOUSI 0.507 → 0.643. Kaksi opetusta: vertailu on luotettavampi ennen
  kuin ehdokkaita on käsitelty eri tavoin, ja 07003 on se scene jossa GT-vapaa
  mittari erehtyy — älä luota siihen siellä ilman GT-tarkistusta.
  `core/qa/runlog.py` tallentaa valinnan pisteet, ja juuri se paljasti ettei
  `normals` tullut valituksi missään aineistossa: kellarin parannus tuli
  `drop_skew`-korjauksesta, ei uudesta detektorista.

- **DETEKTORI ILMAN KARSINTAA EI OLE DETEKTORI — mittaa se putken läpi.**
  Normaalipohjainen seinähaku (`wall_normals.py`) toimi erillisenä skriptinä
  kellarissa loistavasti mutta Rohbaussa surkeasti, ja päättelin siitä että
  menetelmä ei yleisty. Se oli väärä johtopäätös: skripti ohitti koko
  semantics-ketjun, joka on rakennettu juuri palkkilinjojen ja pilaririvien
  karsintaan. Sama menetelmä rekisteröitynä detektorina, saman ketjun läpi:
  | scene_07004 | skriptinä | putken läpi |
  |---|---|---|
  | GT-kattavuus | 0.052 | **0.554** |
  | GT-tarkkuus | 0.260 | **0.955** |
  Älä koskaan vertaa prototyyppiä tuotantoon ennen kuin molemmat ovat kulkeneet
  saman ketjun. **Sama koskee GT-vapaata mittaria**: se erotteli raa'an
  prototyypin ja tuotannon välillä väärin (2/5), mutta kun molemmat ajettiin
  putken läpi, se osui **5/5**.
- **UUDEN MENETELMÄN EI TARVITSE VOITTAA KAIKKIALLA.** Viisi peräkkäistä
  korjausyritystä kaatui siihen että ne yrittivät tehdä YHDESTÄ menetelmästä
  kaikkiin rakennuksiin sopivan, ja jokainen paransi yhtä aineistoa ja rikkoi
  toisen. `_best_detector` ajaa ehdokkaat ja valitsee mitatusti, joten uusi
  menetelmä tarvitsee vain voittaa siellä missä se on aidosti parempi.
  Mitattu: `normals` voittaa kellarissa (0.226 vs contour 0.045) ja Rohbau
  scene_07003:ssa myös GT:llä (0.839 vs 0.807), ja häviää muissa neljässä —
  valinta ottaa sen vain siellä missä se voittaa.
- **KUVA KERTOO SEN MITÄ LUKU EI.** `data/_model_view.py` piirtää pohjan, 3D:n
  ja leikkauksen samasta mallista. Kellarissa kaikki tuotantovariantit
  (contour 23, histogrammi 58, normals 168 seinää) näyttivät kuvassa
  ahtautuvan SAMAAN nurkkaan, kun sama normals-menetelmä skriptinä kattoi koko
  rakennuksen — se johti oikeaan diagnoosiin (karsintaketju) jota pelkät
  kattavuusluvut eivät olisi paljastaneet. Aja se aina uudesta aineistosta.

- **Kerrosjako oli kiinni TIHEYDESSÄ, ja se sotki kaiken muun.** Sama scene,
  sama geometria, vain harvennus eri: Rohbau scene_07000 antoi 1 kerroksen
  pistevälillä 4, 10 ja 70 mm mutta **2 kerrosta** pistevälillä 17 ja 35 mm.
  Kun se jakautui, palkit menivät kahteen kerrokseen ja `floor_00` jäi tyhjäksi
  — palkkikattavuus 0.857, 0.929, **0.000**, **0.000**, 0.857 vaikka detektori
  yksin antoi 12/14 joka tiheydellä. Sama epävakaus liikutti seinäkattavuutta
  välillä 0.327–0.490. **Jos jokin luku heittelee harvennuksessa, älä etsi
  syytä siitä detektorista jonka luku heittelee — etsi se siitä mikä päättää
  MIHIN rakennus katkaistaan.**
- **Pintapari ei ole pelkkä leveys.** Vanha sääntö hyväksyi 100–600 mm levyisen
  piikkiryhmän välipohjaksi. Mitattu scene_07000 voxelilla 20: ryhmä z
  5363..5563 on 200 mm leveä mutta sen sisällä binit ovat 198 868 ja 263 273 —
  ei yhtään tyhjää. Se on yksi paksu pinta (palkiston alapinta). Aidon laatan
  sisällä on umpibetoni eikä betoni palauta pistettä. Tyhjyys on mitattava
  OSUUTENA ryhmän omasta huipusta, ei pistemääränä.
- **Testi joka ei kaadu mutaatiosta ei todista mitään.** Kirjoitin
  kerrosjakokorjaukselle testin `detect_floors`-tasolle; se meni läpi myös
  ilman korjausta, koska synteettinen fikstuuri ei koskaan päässyt sille
  portille asti. Kirjoita testi sille tasolle jolla se oikeasti mittaa
  väitettään, ja **tarkista mutatoimalla** että se kaatuu ilman korjausta.
- **Aukkokattavuus ei voi ylittää seinäkattavuutta.** 50/113 Rohbaun
  GT-aukosta istuu seinillä joita mallissa ei ole; yksikään niistä ei löydy
  eikä voi löytyä. Aukkodetektorin oma luku on 19/63 = 0.302, ei 19/113.
  `data/_opening_qa.py` erottelee nämä (`ISANTASEINA MALLISSA` vs `PUUTTUU`).
  **TARKENNUS 26.8.2026 — 0.302 on YHÄ liian ankara.** `data/_opening_probe.py`
  ajettuna scene_07000:n 16 löytymättömälle aukolle:
  | syy | kpl |
  |---|---|
  | **ei reikää pilvessä** (täyttö 1.00 aukon kohdalla = umpinainen seinä) | **9** |
  | seinä itsekin tyhjä (valeseinä) | 2 |
  | reikä näkyy, detektori ei löydä | **5** |
  Yhdeksää aukkoa ei voi löytää millään säännöllä (yksin `wall_008`:lla kuusi).
  **Detektorin oma suoritus on 8/13 = 0.615 siitä mikä on löydettävissä**, ja
  aitoa varaa on viisi aukkoa — ei kaksitoista. Aja `_opening_probe.py` ennen
  kuin aukkoihin käyttää aikaa; kolme neljästä "puutteesta" on keilausvarjo.
  Niistä viidestä yksi on 3527 mm leveä (yli `_MAX_W` 3000), loput 2278–2795 mm
  eli leveysportti ei niitä estä — syy on muualla (reunaehto/korkeusprofiili).
  **Läpiviennit eivät kuulu nimittäjään:** Rohbaun `WallCutout`-instanssit ovat
  mitattuna 544 × 423 mm ja mediaani-alareuna 8998 mm lattiasta, eli putki- ja
  kanavaläpivientejä katonrajassa. `_MIN_H = 600` hylkää ne oikein.

- **Portti joka mittaa NÄKYVYYTTÄ hylkää sen mitä ei nähdä, ei sitä mikä on
  väärin.** Palkkien kiinnitysportti (`_attached`) vaati, ettei alapinnan ja
  laatan välissä ole 300 mm tyhjää. Korkeassa tilassa lattialta keilattaessa
  palkin uuma on katsomissuunnan takana eikä sitä skannata lainkaan, joten
  portti hylkäsi aidon palkin siitä ettei sitä nähdä. Ablaatio kaikilla viidellä
  Rohbau-scenellä (`data/_beam_attach_abl.py`): portti päällä 39/77 tarkkuudella
  0.824, pois 62/77 tarkkuudella 0.808 — **23 aitoa palkkia hinnaksi 0.016
  tarkkuudesta**. Liiketila-S, liiketila-L ja asunto antoivat TÄSMÄLLEEN saman
  tuloksen kummallakin (`_beam_attach_abl2.py`), eli portti ei estänyt niissä
  mitään. Kysy jokaisesta portista: mittaako se rakennetta vai skannerin
  sijaintia? Jälkimmäinen ei yleisty.
- **Solun MINIMI on tiheysmittari, ei geometriamittari.** 200 mm solussa on
  4 mm skannissa ~2500 pistettä ja 70 mm skannissa ~8, joten yksi harhapiste
  (kaapeli, putki, kohina) painaa solun alapinnan alas sitä varmemmin mitä
  tiheämpi skanni on — ja `z_free`n alle painunut solu POISTETAAN kartasta, eli
  tiheys repii laikun palasiksi eikä vain siirrä sitä. Sama koskee jokaista
  `.min()`- ja `.max()`-tilastoa solua kohti. Korvaa PINNALLA: alin taso jonka
  ympärille kertyy OSUUS solun omista pisteistä. Osuus on tiheysriippumaton.
  Mitattu: kattavuus säilyi 12/14 joka tiheydellä, tarkkuus 0.838 → 0.866 …
  0.882 → 0.911 (`data/_beam_density.py`).
- **Aja tiheyssweep ennen kuin lupaat mitään tuntemattomasta skannista.**
  `data/_beam_density.py` ja `data/_density_sweep.py` ajavat SAMAN tilan usealla
  pistevälillä. Jos tulos muuttuu, mittari on sidottu skannin tiheyteen eikä
  rakennukseen. Tämä paljasti `_attached`in: koko putken kattavuus heitteli
  0.000 ja 0.643 välillä pelkästä harventamisesta, ja HARVA pilvi voitti tiheän.
- **Väärä mittari on pahempi kuin ei mittaria.** `_beam_qa` raportoi palkin
  leveydeksi maailman akselien mukaisen laatikon, joten vino 27 m palkki näytti
  5458 mm leveältä kun se on 1464. Luku sai GT-palkit näyttämään `_MAX_WIDTH`in
  rikkojilta ja ohjasi etsinnän väärään porttiin. Instanssin mitat on luettava
  sen OMALTA akselilta (PCA), ei maailman akseleilta.
- **Yksikkötunnistus ei saa nojata rakennuksen kokoon.** Vanha sääntö oli
  "laajuus < 200 → metrit"; 250 m halli metreissä jäi skaalaamatta ja koko putki
  mallinsi 250 mm rakennuksen ilman yhtään virhettä. Pisteväli erottaa yksiköt
  koosta riippumatta: mitattu Rohbau (metrit) 0.016–0.024, mm-pilvet 2–124.
  `loader.metre_scale` on ainoa paikka jossa sääntö saa olla.

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
  avautua.
- **"Pää osuu seinään" ei vielä tarkoita että nurkka on olemassa.** Kaksi
  kattamatonta häntää voi kohdata TOISENSA: kumpikaan pää ei ole irrallaan,
  mutta nurkka lepää tyhjän päällä (asunnossa wall_002 ↔ wall_010). Oikea
  kysymys on **onko vastinseinällä pintaa juuri liitoskohdassa** — ei se onko
  siellä seinäOBJEKTI. Tämä löysi scene_07000:sta katvepintaseinän joka oli
  14.4 m liian pitkä ja jonka kaistasta poistui 392 GT-pistettä 201 037:stä.
  Kontrolli: 21 m leikattu viidessä scenessä, kattavuus/tarkkuus ennallaan
  (suurin muutos 5 desimaalilla 0.87755 → 0.87746). Aito nurkka jää: asunnon
  wall_005:n 800 mm häntä päättyy `wall_ext_002`:een joka ON katettu
  liitoskohdassa.
- **Lue kate KAIKILTA seiniltä ennen kuin leikkaat yhtäkään.** Jos vastinseinän
  katteen lukee jo leikatusta akselista, ensimmäinen leikkaus muuttaa
  seuraavan tuomion ja tulos riippuu seinien järjestyksestä.
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

- **KORJAUS EDELLISEEN: instanssikattavuus 0.30–0.49 EI TARKOITA että puolet
  seinistä puuttuu.** Kun sama luku jaetaan sen mukaan onko GT-seinä MALLIN
  JALANJÄLJEN sisällä (seinäakselien konveksi peite, `data/_wall_inst_qa.py`):
  | scene | jalanjäljen SISÄLLÄ | ULKOPUOLELLA | yhteensä |
  |---|---|---|---|
  | scene_07000 | **17/17 = 1.000** | 7/32 = 0.219 | 24/49 |
  | scene_07002 | 12/23 = 0.522 | 4/21 = 0.190 | 15/44 |
  | scene_07003 | **7/7 = 1.000** | 1/20 = 0.050 | 8/27 |
  Eli scene_07000 ja scene_07003 ovat **täydellisiä sillä alueella jonka malli
  väittää mallintavansa**, ja koko vaje on siitä että RAKENNUS JATKUU mallin
  rajauksen yli. Kuva (`data/_gap_view.py` ja jäännösehdokkaiden overlay)
  näyttää sen suoraan: puuttuvat GT-seinät ovat perimetrin ULKOpuolella.
  Tämä selittää kolme muuta havaintoa kerralla:
  - "histogrammi löytää vain hallitsevat seinälinjat" — jalanjäljen sisällä
    MUITA seiniä ei ole;
  - "1–2 m seiniä ei löydy yhtään" — ne ovat kaikki ulkopuolella;
  - jäännösseinähaku romahdutti tarkkuuden — se lisäsi seiniä alueelle jota ei
    ole kunnolla keilattu.
  **Ainoa aito seinävaje on scene_07002:n 11 instanssia jalanjäljen sisällä.**
  Se on oikea kohde; älä optimoi kokonaislukua 0.49 vasten.

- **PISTEKATTAVUUS PIILOTTAA PUUTTUVAT SEINÄT — MITTAA INSTANSSIT.**
  `data/_rohbau_qa.py` antaa seinille kattavuuden 0.81–0.89, ja se on totta:
  perimetriseinillä on valtaosa pisteistä. `data/_wall_inst_qa.py` laskee saman
  GT-instansseina (≥2000 pistettä, ≥30 % pisteistä mallin kaistassa):
  | scene | pistekattavuus | INSTANSSIkattavuus | mallin seiniä |
  |---|---|---|---|
  | scene_07000 | 0.887 | **24/49 = 0.490** | 8 |
  | scene_07002 | 0.860 | **15/44 = 0.341** | 8 |
  | scene_07003 | 0.807 | **8/27 = 0.296** | 7 |
  Puuttuvien joukossa on 8.5 m, 5.4 m ja 3.7 m seiniä. Sama nimittäjäharha joka
  piilotti palkkien 0/77:n: iso pistemäärä yhdessä elementissä peittää monta
  puuttuvaa pientä. **Optimoi instanssikattavuutta, älä pistekattavuutta.**
  Tämä selittää myös aukot: 19/35 GT-aukosta on seinällä jota mallissa ei ole
  (`data/_opening_view.py`, mitattu etäisyys lähimpään mallin seinään 2.3–9 m).
  **Pituusluokittain (neljä sceneä, sama kuvio joka kerta):**
  | luokka | 07000 | 07002 | 07003 | 07004 |
  |---|---|---|---|---|
  | yli 4 m | 0.80 | 1.00 | 0.67 | 0.83 |
  | 2–4 m | 0.43 | 0.29 | 0.27 | 0.27 |
  | 1–2 m | **0/3** | **0/7** | **0/2** | **0/1** |
  Malli saa pitkät seinät ja menettää keskipitkät; 1–2 m seiniä ei löydy
  yhtään (0/13 yhteensä).
  **KUMOUTUNUT SELITYS — `wall_histogram._MIN_WALL_LENGTH` ei ole syy.** A/B
  scene_07000:lla koko putkella (2000 vs 1200 mm): **kaikki luvut identtiset**
  — 24/49 instanssia, pistekattavuus 0.887, tarkkuus 0.924, 0 ongelmaseinää,
  samat pituusluokat. Syy näkyy mallista: histogrammidetektori tuotti
  **4 seinää ja kaikki ovat 27–30 m** (loput 2 ovat `floorplan`- ja 2
  `second_face`-seiniä). Kynnys ei sido, koska lyhyestä seinästä ei synny
  globaalia piikkiä lainkaan. **Histogrammi mallintaa vain hallitsevat
  seinälinjat** — lyhyet väliseinät ovat menetelmän ulkopuolella, eivät
  kynnyksen takana.
  **JÄÄNNÖSSEINÄHAKU: rakennettu, mitattu ja KYTKETTY POIS (18.8.2026).**
  Puuttuvat seinät ovat pilvessä yhtenäisinä pintoina — kun mallin seinien
  lunastamat pisteet poistetaan, jäännöksessä on 15 suoraa 1.2–5.6 m rakennetta
  joiden GT-luokka on 92–100 % Wall (`data/_residual_walls.py`).
  `semantics/residual_walls.py` tekee niistä ehdokkaita, ja se TOIMII siihen
  mihin se rakennettiin: **1–2 m seinät 0/3 → 3/3**. Mutta koko mallin luvut:
  | mittari | ilman | kanssa |
  |---|---|---|
  | instanssikattavuus | 24/49 | 23/49 |
  | pistekattavuus | 0.887 | 0.830 |
  | **tarkkuus** | **0.924** | **0.515** |
  | ongelmaseiniä | 0 | 13 |
  Syy on mitattu: ehdokkaista vain **8/15 on GT-seiniä**, ja
  `prune_unsupported_walls` **suojaa alle 4 m seinät joilla on pintaa** — sama
  suoja joka pelastaa aidot lyhyet seinät päästää nämä läpi. Ehdokkaan on siis
  todistettava itsensä jo syntyessään, ei toivottava karsinnan hoitavan sen.
  **Kaksi ansaa matkan varrelta, molemmat mitattuja:**
  - *Ehdokas voi olla olemassa olevan seinän toinen pinta.* Liian ohueksi
    mallinnetun seinän ulkopinta jää lunastamatta; deduplikointi sulautti
    ehdokkaat oikeisiin seiniin ja LYHENSI niitä (0.887 → 0.689, 30.3 m seinä
    katkesi 15.4 m:iin). Siksi ehdokas joka on samansuuntainen ja alle 600 mm
    päässä olemassa olevasta seinästä pudotetaan.
  - *Kaista ja pystyulottuvuus eivät saa olla osuuksia huonekorkeudesta.*
    10 m hallissa kaista alkoi 2.5 m:stä (ohi seinäpinnan alaosan) ja
    pystyehto vaati 2.8 m kun kaukaisesta seinästä näkyy 1.8–2.2 m. Ehdokkaita
    1 → 15 kun molemmat muutettiin fysikaalisiksi (900 mm / 800 mm).
  - *Sijoitus putkessa ratkaisee.* Geometriaketjun SISÄLLÄ ehdokkaat
    osallistuivat suoristukseen ja nurkkien napsautukseen ja muokkasivat
    oikeita seiniä (tarkkuus 0.538, lipulla 6 alkuperäistä histogrammiseinää).
  **LIITTYVYYS MITATTU JA KUMOUTUNUT — ja se menee VÄÄRINPÄIN.** Ajatus: aito
  seinä päättyy toiseen seinään, pilariin tai perimetriin; irrallinen levy ei.
  Mitattu scene_07000:n 15 ehdokkaasta (etäisyys lähimmästä päästä mihin
  tahansa muuhun seinään):
  | ehdokkaat | lähin pää, mediaani |
  |---|---|
  | GT-seiniä | **1269 mm** |
  | muut | **200 mm** |
  Aidot seinät ovat runkovaiheessa irrallisia tynkiä, ja "None"-krääsä on
  nimenomaan kiinni mallinnetuissa seinissä. Liittyvyysehto poistaisi aidot ja
  säilyttäisi roskan. **Neljäs kumoutunut erottelija** (tuki/jatkuvuus
  karsinnan kautta, lähisuodatus, pystyulottuvuus, liittyvyys).
  **VAROAUMA MITTARIIN:** Rohbaun luokka 0 = None on LUOKITTELEMATON, ei
  "ei-seinä". Kuusi 15:stä ehdokkaasta on None-voittoisia, joten "8/15 aitoja"
  on alaraja eikä välttämättä totuus. Ennen viidettä erottelijayritystä
  kannattaa katsoa kuvasta (`data/_gap_view.py`-tyyliin) mitä ne None-pinnat
  oikeasti ovat — muuten viritetään erottelijaa väärää totuutta vasten.


  **HUOM reititysvalinta on tehty PISTEkattavuudella.** "Liiketila → histogrammi"
  perusteltiin +0.234 pistekattavuudella vs −0.027 tarkkuudella. Tänään
  opittiin että pistekattavuus on painotettu elementin koolla, joten se on juuri
  se mittari joka suosii neljää 30 m seinää. **Mittaa reititys uudelleen
  instanssikattavuudella ennen kuin siihen nojaa.**
  **RATKAISTU OSITTAIN (21.8.2026): reititystä ei enää arvata, se mitataan.**
  `_looks_like_retail`/`is_large` valitsee nyt vain EHDOKKAAT; `_best_detector`
  ajaa ne ja valitsee sen jonka `core/qa/coverage.py::wall_coverage` on suurin.
  Valittu on siis määritelmän mukaan vähintään yhtä hyvä kuin vanha reititys.
  Mitattu koulun kellarilla (5697 m², matala ja sokkeloinen): histogrammi 0.009
  ja 6 seinää, contour 0.045 ja 23 seinää → putki valitsee nyt contourin ja
  antaa 23 seinää ja 4 tilaa entisen 6:n ja 1:n sijaan.
  **Mittari on silti PISTEpohjainen eli sama painotusharha koskee sitä.**
  Kellarin ero on 5-kertainen eikä muutu painotuksesta, mutta ennen kuin
  valintaan lisätään uusia ehdokkaita, se on mitattava myös instansseina.

- **AUKOT ON NYT MITATTU GT:tä VASTEN ENSIMMÄISTÄ KERTAA (18.8.2026).**
  `data/_opening_qa.py`, Rohbau site_07 (86 GT-aukkoinstanssia viidessä
  scenessä; runkovaiheessa ikkuna-aukot ovat luokassa 7 = Wall Cutout, ei 13):
  | scene | GT-aukkoja (≥500 pist.) | löydetty | mallin aukkoja | tarkkuus |
  |---|---|---|---|---|
  | scene_07000 | 35 | 4 | 8 | **0.500** |
  | scene_07002 | 23 | 6 | 10 | **0.500** |
  Eli **kattavuus 0.11–0.26 ja joka toinen mallin aukko ei ole GT-aukon
  kohdalla.** MUTTA nimittäjä on väärä: `data/_opening_view.py` osoittaa että
  **19/35 GT-aukosta on seinällä jota mallissa ei ole** (2.3–9 m lähimpään
  mallin seinään), ja niistä 12:sta jotka ovat mallinnetulla seinällä vain
  **5:llä näkyy reikä pilvessä** (`data/_opening_probe.py`: täyttö aukon kohdalla
  0.25–0.42 vs 0.64–0.89 vieressä). Aukkodetektorin oma osuus on siis
  **4–5 / 9–10**, ei 4/35. Loput on seinäkattavuuden ongelma.
  **Korjattu tästä yksi asia mitattuna:** `_MAX_W` 2500 → 3000 mm (runkovaiheen
  oviaukot ovat 2.5–3.0 m). scene_07000 5/35 → 6/35 ja tarkkuus 0.312 → 0.353,
  scene_07003 2/19 → 3/19 ja 0.500 → 0.600; asunto ja liiketila ennallaan. Tämä on lähtöluku, ei tavoite — sama tilanne kuin palkeissa ennen
  alapintamallia (0.048). Älä väitä aukkojen toimivan ennen kuin tämä on ajettu.

- **PALKKI ON ALAPINTA, EI PISTEKLUSTERI.** Vanha detektori klusteroi
  kattokaistan pisteet XY:ssä ja luki palkin leveyden klusterin XY-laajuudesta.
  Skannattu palkki ei ole umpikappale vaan **kaksi pystypintaa ja niiden
  välinen alapinta**, joten klusterin leveys ei koskaan ollut palkin leveys:
  synteettisen liiketilan sama 300 mm palkki antoi joko **143 mm** (yksi pinta
  omana klusterinaan → hylky `_FINISHED_MIN_WIDTH` 150) tai **47 000 mm** (koko
  palkisto ketjuuntui pilarien kautta yhdeksi klusteriksi → hylky `_MAX_WIDTH`
  600). Kumpikin hylättiin, ja koko detektori sai GT:tä vasten **tarkkuuden
  0.048 ja kattavuuden 0/77**.
  Uusi malli (`beam_detector.py`, 18.8.2026) mittaa sen mitä keilain näkee:
  jokaiselle 200 mm XY-solulle **kattokaistan alin piste = alapinta**,
  vierekkäiset samankorkeat solut = laikku, ja laikun poikittaisleveys ON
  palkin leveys. Mitattu (`data/_beam_qa.py`, `data/_beam_synth_qa.py`):
  | aineisto | vanha | uusi |
  |---|---|---|
  | Rohbau site_07, instanssikattavuus | **0/77** | **34/77** |
  | Rohbau tarkkuus (07000 / 07002 / 07003 / 07004) | 0.048 / – / – / – | **0.83 / 0.84 / 0.82 / 0.96** |
  | synteettinen liiketila, GT-akselipituudesta katettu | **0.012** | **0.856** |
  | synteettinen liiketila, tarkkuus / harhapalkit | 1.000 / 0 | **1.000 / 0** |
  | asunto (hormi) | 1 valepalkki | **0** |
  Sama mitattiin koko putken läpi PointNet-suodattimen kanssa: **luvut eivät
  muutu** (0.856 / 1.000), eli suodatin ei syö alapintoja.
  **Alapintaehto korvaa neljä aiempaa erikoissääntöä.** Seinä, pilari, hyllykkö,
  gondoli ja asunnon hormi yltävät lattiaan, joten niiden alin piste ei ole
  koskaan katon lähellä eikä niistä synny laikkua. Asunnon `beam_000`-hormille
  yritettiin kolmea eri sääntöä (alaslasketun katon reuna, `_has_headroom`-
  resoluutio, soffitin ja esteen väli) ja kaikki kumoutuivat mittauksessa —
  oikea korjaus oli vaihtaa malli, ei lisätä viides sääntö.
  **Portit ja mistä ne on mitattu** (`data/_soffit_sweep.py` ajaa kaikki
  scenet ja tulostaa jokaisen laikun mitat GT-luokan rinnalla):
  aspekti ≥ 3, pituus ≥ 1200, leveys ≤ 3000, syvyys ≥ 150, solut ≥ 20,
  **täyttöaste ≥ 0.5** (laikun solut / suorakaiteen solut — nosti Rohbaun
  tarkkuuden 0.808 → 0.834 **kattavuuden muuttumatta**; kulmassa kääntyvä
  kanava täyttää 31 %), ja ilmarako laattaan ≤ 300 mm.
  **ANSA — ilmarakoa ei saa mitata laatikon korkeimmasta pisteestä.** Laatan
  oma pinta on aina laatikossa, joten `max(z)` on aina katossa ja testi on
  turha. Se mitataan laikun sisältä pystyhistogrammina (pisin tyhjä jakso).
  **ANSA — vuotava vesiväritäyttö.** Naapuriehto yksin (|Δz| ≤ 150 mm)
  ryömii portaittain läpi koko mallin: mitattu **200 m "palkki"**. Laikkuun
  tarvitaan myös ankkuriehto ensimmäiseen soluun.

- **PALKIN KATTAVUUDEN TULPPA ON KEKSITTY KERROSJAKO, EI PALKKIDETEKTORI.**
  scene_07001 ja scene_07004 jäävät instanssikattavuuteen 0.21 ja 0.36, muut
  kolme ovat 0.53–0.60. Syy on mitattu: näissä kahdessa `detect_floors`
  (`geometry/floor_splitter.py`, `_split_tall_slice`) **keksii toisen kerroksen
  palkiston alapinnan kohdalle** — floor_00 on −2052…5444 ja floor_01
  5444…8076, eli palkit katkeavat kesken. `_SLAB_PEAK_FRAC = 0.30` on
  suosioääni: 10 m korkeassa hallissa palkiston alapintapiikki (2.9 M pistettä)
  on isompi kuin oikea kattopiikki (2.8 M). Muissa kolmessa scenessä jakoa ei
  synny ja kattovirhe on −99…+4 mm.
  **KUMOUTUNUT KORJAUSEHDOTUS — jalanjäljen peitto ei erota välipohjaa
  palkiston alapinnasta.** Ajatus oli että aito välipohja peittää koko pohjan
  ja palkkikaistat vain osan. Mitattu (400 mm solut, ±60 mm kaista):
  | taso | 07001 | 07004 | 07000 |
  |---|---|---|---|
  | lattia | 0.33 | 0.39 | 0.39 |
  | palkiston alapinta ~5450 | **0.29** | **0.30** | 0.27 |
  | aito katto ~8080 | **0.10** | **0.09** | 0.12 |
  Erottelu menee **väärinpäin**: aito katto saa pienimmän peiton, koska palkisto
  varjostaa sen alhaalta keilattaessa. Älä yritä tätä uudelleen.
  **KUMOUTUNUT KORJAUSEHDOTUS 2 — pintapari ei myöskään erota.** Ajatus oli
  että välipohja on alapinta + kävelytaso 150–500 mm ylempänä samassa solussa,
  kun palkin alapinnan yläpuolella on tyhjää lakeen asti. Mitattu
  `data/_slab_pair_probe.py`, scene_07001 (400 mm solut, ±60 mm kaista):
  | taso | pintaa 150–500 mm YLÄPUOLELLA | pintaa ALAPUOLELLA |
  |---|---|---|
  | lattia −2081 | 0.15 | 0.09 |
  | palkiston alapinta 5450 | **0.53** | 0.26 |
  | aito katto 8080 | 0.01 | 0.49 |
  Taas **väärinpäin**: palkiston alapinta saa suurimman arvon, koska palkin omat
  pystykyljet ja lakipinta täyttävät ikkunan. Kaksi kumoutunutta ehdokasta —
  seuraava yritys ei saa olla kolmas muunnelma vaakapinnan tiheydestä.
  **KUMOUTUNUT KORJAUSEHDOTUS 3 — kävelytaso ei myöskään erota.** Ajatus:
  aito kerros on jakotason varassa, eli ylemmän viipaleen soluista valtaosan
  alin piste on jakotasolla. Mitattu `data/_split_floor_probe.py`: keksitty
  jako 07001 **0.66**, 07004 **0.68**, aito lattia 07000 **0.61**. Ei eroa.
  **RATKAISU — PINTAPARI, ei pinnan tiheys.** Kerrosjako on kaksi vaakapintaa:
  alemman kerroksen katto JA ylemmän lattia. Palkiston alapinta on YKSI pinta.
  Mitattu 700 mm ikkunassa jakotason ympärillä (25 mm binit, ≥30 % maksimista):
  | aineisto | taso | pintoja |
  |---|---|---|
  | test_multiscan (aito 2 kerrosta) | 3150 | **2** — 3000 ja 3296 |
  | Rohbau 07001 | 5450 (palkiston alapinta) | **1** |
  | Rohbau 07004 | 5442 | **1** |
  | Rohbau, rakennuksen lattia / katto | −2081 / 8080 | 1 / 1 (oikein) |
  `_split_tall_slice` vaatii nyt sisäiseltä laatalta pintaparin 100–600 mm.
  Tulos: 07001 ja 07004 eivät enää pilkkoudu, test_multiscan pilkkoutuu yhä.
  **ANSA — `tests/test_floor_splitter.py`:n välipohja oli YKSI pinta.** Fixture
  ei siis erottanut kerrosjakoa palkiston alapinnasta eli koodasi juuri tämän
  bugin. Se on nyt kaksi pintaa (3000 + 3300) kuten aidossa keilauksessa.
  **Tulos palkeille:** scene_07001 instanssikattavuus 0.21 → **0.42** ja
  tarkkuus 0.354 → **0.812**; scene_07004 kattavuus 0.36 (ennallaan), tarkkuus
  0.963 → 0.810. Kaikki viisi sceneä yhteensä **38/77** (alun perin 0/77).

- **PILARI EI AINA YLLÄ LATTIASTA KATTOON — JA SE OLI DETEKTORIN OLETUS.**
  `detect_columns` laski solun pystytäytön OSUUTENA koko huonekaistasta
  (`_VFILL_MIN` 0.70) ja kirjasi `base_z = floor_z` kysymättä. Rohbau site_07:n
  pilarit kantavat palkistoa ja ovat 3.1 m korkeita 9.2 m kaistassa → osuus
  0.31, eivätkä koskaan päässeet ehdokkaiksi. Mitattu `data/_column_qa.py`:
  **0/15 instanssia, 0 pilaria mallissa.**
  Korjattu: täyttö mitataan YHTENÄISENÄ jaksona ja jakso on myös pilarin
  mitattu `base_z` ja `height`. Vaatimus on `min(0.70 × kaista, 2300 mm)`,
  joten matala huone toimii kuten ennen. Poikkileikkauksen vakaus ja
  vyötärötesti ajetaan nyt jäsenen omassa jaksossa, ei huoneen kaistassa.
  **KESKEN — tämä EI vielä riitä.** GT-pilarit muuttuvat nyt ehdokkaiksi
  (jokaisella on 3200–3400 mm yhtenäinen jakso ja komponentti joka läpäisee
  ext-portin), mutta jokin myöhempi portti pudottaa ne yhä: mitattu edelleen
  **0/15**, ja mallin 4 pilaria eivät ole GT-pilareita. Estävää porttia ei ole
  eristetty — ehdokkaat ovat 2–4 solun kokoisia (pilarista näkyy 1–2 kylkeä),
  joten epäillyt ovat footprint-, aspekti- ja `_surrounded`-portit.
  Liiketilan 34/34 pilaria säilyivät muuttumattomina, joten muutos ei maksanut
  mitään — mutta älä väitä pilareita korjatuiksi.
  **ESTÄVÄT PORTIT ON NYT ERISTETTY** (`data/_col_gate_gt.py`, scene_07000):
  | syy | GT-pilareita | mitat |
  |---|---|---|
  | seinäetäisyys < 250 mm | **6/15** | 29, 30, 36, 123, 124, 125 mm |
  | aspekti > 2.5 tai ohut footprint | **7/15** | 52×199 … 112×303 mm |
  | muut | 2/15 | |
  Molemmat mittaavat **keilauspeittoa, eivät jäsentä**: 600 mm pilarista näkyy
  yksi kylki, joten poikkileikkaus mittautuu 52×199 mm siivuksi.
  **KUMOUTUNUT KORJAUS A — poikkileikkaus säteeltä jäsenen omassa jaksossa.**
  Ajatus: kerää pisteet `_MAX_FOOTPRINT`-säteeltä eikä pelkistä täyttösoluista.
  Mitattu: säde nielaisee viereisen massan → footprint-portti hylkää kaiken,
  **Rohbau 0, liiketila 34 → 0**. Selvä regressio.
  **KUMOUTUNUT KORJAUS B — yksi kylki = neliöprofiili.** Ajatus: alle 150 mm
  paksu siivu on yksi keilattu kylki, jolloin aspekti ei kelpaa hylkyperusteeksi
  ja seinänpalan erottaa rengastesti. Mitattu: Rohbau 4 → **8 pilaria mutta
  yhä 0/15 GT ja tarkkuus 0.000** (löydetyt ovat 0.9–14.6 m päässä lähimmästä
  GT-pilarista), liiketila pysyi 34. Eli se vain tuplasi valepositiiviset.
  **KORJAUS OMAAN PÄÄTELMÄÄN — Rohbau site_07:ssa EI OLE vapaita pilareita.**
  Kun aspektiportti relaksoidaan pois, **13/15 GT-pilaria hylkääntyy
  seinäetäisyyteen 9–125 mm** ja loput 2 ohueen footprintiin. Lähimmät seinät
  ovat aitoja (GT-kaista 88–95 % Wall), ja **pilarin kohdalla seinän kaistassa
  on 15–44 % Column-pisteitä**: pilari työntyy seinälinjasta ulos 359–508 mm.
  Nämä ovat siis **pilastereita — seinään integroituja pilareita** — ja
  seinämalli kulkee niiden läpi. Erillinen `IfcColumn` päällekkäistäisi
  geometrian jonka seinä jo mallintaa, joten seinäetäisyysportti tekee tässä
  oikein. **0/15 ei ollut koskaan saavutettavissa.**
  Älä siis lue tästä että pilaridetektori on rikki: ainoa aineisto jossa on
  vapaita pilareita on synteettinen liiketila, ja siellä se on **34/34**.
  Aito puute on toisaalla: 105–150 mm seinä jonka läpi kulkee 400–500 mm
  pilasteri mallintuu vakiopaksuisena. Se on SEINÄN paksunnos, ei pilari.
  **Ennen kuin pilaridetektoria kosketaan, hanki aineisto jossa on vapaita
  pilareita** — muuten sitä viritetään totuutta vasten jota ei ole.


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
  3. ~~AUKI: lattia-katto-hylly AIVAN seinää vasten (30–50 mm irti) jää
     valeseinäksi~~ **KORJATTU (22.8.2026)**: `remove_shelf_front_walls`
     hyväksyy nyt liiketilassa myös 15–150 mm etäisyyden (`_SKIN_MIN`/
     `_SKIN_MAX`). Raja on fysikaalinen eikä viritetty: ohuinkin seinä on
     66 mm, joten sitä lähempänä oleva rinnakkainen pinta ei voi olla oma
     seinänsä. Mitattu: union-kokeessa syntyi neljä hyllyvaleseinää 32–33 mm
     perimetristä → 0, GT-kattavuus 8/9 säilyi. Tuotanto ennallaan
     (retail_s 9/9 GT-seinää, 0 ylimääräistä, 0.724/0.842).
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

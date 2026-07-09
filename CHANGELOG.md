# Muutosloki

Versiointi: `vMAJOR.MINOR.PATCH`. Releaset julkaistaan
[`Mcrauli/scan2bim-web`](https://github.com/Mcrauli/scan2bim-web/releases):iin;
sovellus päivittää itsensä sieltä.

## v0.7.1 (9.7.2026) — yhden tiedoston polku käyttää tuotantoputkea (kaatumiskorjaus)
- **Yksi skanni GUI:sta ei enää kaadu isoilla/katkenneilla tiedostoilla.** GUI ajoi
  yksittäisen tiedoston vanhalla `Pipeline.run()`-polulla (koko pilvi kerralla
  muistiin, ei lohkolukua, ei kerrosjakoa) — iso E57/PLY (esim. ConSLAM 159 M)
  kaatui `'NoneType' object has no attribute 'write'` -virheeseen windowed-exessä.
  Nyt sekä yksi että monta tiedostoa käyttävät `run_floors`-tuotantoputkea
  (lohkoluku, kerrosjako, diagnostiikka). **Tämä on pilotin yleisin tapaus (yksi E57).**
- **Windowed-exe:n None-virrat** (`sys.stdout`/`stderr` = None) ohjataan lokitiedostoon
  ennen importteja → mikään print/logging ei enää voi kaataa sovellusta.

## v0.7.0 (9.7.2026) — jättiskannit + liiketilamoodi + suodattimen isot korjaukset + pilarit/palkit
- **Jättiskannit (satoja M pistettä) eivät enää kaada muistia eivätkä jumita.**
  Testattu: 159 M pisteen skanni koko pipelinen läpi (aiemmin OOM/jumi).
  - Binääri-PLY luetaan LOHKOISSA ja Z-kaista suodataan lukiessa → huippumuisti
    on yksi lohko, ei koko tiedosto. Kerrostunnistus + z-alue lohkoluvulla
    (159 M: kerrostunnistus 2 min → 3 s).
  - Paksuus- ja refine-pilvet rajataan kattoon satunnaisohennuksella (ei
    voxel-sentroidibiasta → pintamediaani säilyy). Voxeloitavat lataukset
    (detektio) tehdään lohkoittain kevyellä numpy-ruutudedupilla (o3d:n
    voxel-hash söi ~10 GB 70 M pisteelle). Huippumuisti 12 GB → ~3 GB.
  - Alle 40 M pisteen skannit käyttävät entistä (validoitua) latauspolkua
    muuttumattomana — asunto todennettu regressiottomaksi (6/6 seinää ≤ 1,5 mm,
    mediaani 0,06 mm).
- **PointNet-suodattimen lohkojako O(lohkot×pisteet) → ämpärijako.** Iso skanni
  (110×29 m → 13 000 lohkoa × miljoonat pisteet) jumitti minuuteiksi kun jokainen
  lohko skannasi koko pistetaulukon. Nyt pisteet ämpäröidään ruutuihin kerran →
  per-lohko O(1) haku. Tulos tavu tarkalleen identtinen (todennettu). Koski myös
  isoja myymälätiloja.
- **Katkennut/vajaa PLY** havaitaan tavuista: selkovaroitus + roskahännän leikkaus
  (o3d palautti hiljaa roskaa headerin lupaamaan pistemäärään asti).
- **Kohdetyyppi-valinta (GUI): "Liiketila / työmaa"** — oma suodatinmalli joka
  poistaa lattia-katto-hyllyrivit (synteettinen halli: 4 hyllyriviseinää → 0;
  hyllynpoisto 17 % → 95 %). Asunnoissa oletusmalli on tarkempi — siksi valinta,
  ei automatiikka. Molemmat mallit bundlataan exe:hen.
- **Suodattimen maskinsiirtobugi korjattu** (tuotannossa v0.5.0:sta): tasopinnat
  menettivät 20–30 % pisteistä voxel-avainhaussa → työmaaseinistä säilyy nyt
  98 % (oli 60 %). Lattia/katto-kaistat pakkosäilytetään aina.
- **Pilaridetektio uusiksi** (pystypeitto, ei DBSCAN): työmaa-GT 0/92 → 14/38
  ilman että holvituet/tavara sotkevat; väärät seinänpalat karsitaan rengastestillä.
- **Palkkidetektori kytketty pipelineen** (oli irrallaan — palkit olivat aina 0)
  seinäeksluusiolla.
- **Kerrosjako**: haamukerrokset (harhapisteet, <2 % pisteistä) hylätään — 4
  työmaasceneä tuotti aiemmin tyhjän mallin; korkea viipale ilman tyhjää
  z-kaistaa jaetaan sisäisen laattapiikin kohdalta.
- **Diagnostiikkaraportti**: joka ajosta jaettava diagnostics.txt (versio,
  ympäristö, vaihelokit, virheet — ei geometriaa) etätuen tarpeisiin.
- E57-stressitesti: 46 M pisteen Matterport-moniskanni (9 asemaa) läpi
  kaatumatta, mediaani 0.21 mm, roskaseinät flägättyinä.

## v0.6.0 — pintatarkkuus todennettuna raakapilveä vasten + robustisuus

Sisältää myös oviaukkosillan: pystymaskin katkaisema seinä (ovi railossa
kollineaaristen pätkien välissä) yhdistetään ylitysevidenssillä ja
pintakoherenssiehdolla → ovet löytyvät myös seinäjänteiden väleistä.

Rohbau3D-työmaaskannilla (oikea TLS, 11 M pistettä) mallin pinnat olivat
jopa 21 mm pielessä vaikka QA väitti 0.2 mm — QA ja pintalinjaus mittasivat
12 mm voxel-suodatettua pilveä. Nyt molemmat käyttävät 5 mm raakapilveä ja
virheet korjattu: työmaaseinät 0.5–5 mm raakaa vasten (oli 3–21 mm), GT-asunto
0.03 mm, talo 000035 mediaani 0.07 mm (12/13 ≤ 1.5 mm; ainoa ylitys flägätään).
- **Epäsymmetrinen näkyvyys**: aito takapinta 27 % etupinnan tiheydestä jäi
  25 % piikkikynnyksen alle → yksipinta-polku jätti seinän 22 mm pieleen.
  Heikompi piikki (≥8 %) hyväksytään jos se istuu odotetun vastapinnan
  kohdalla (±60 mm) → 219 mm betoniseinä mitataan oikein (GT-labelit
  vahvistivat molemmat pinnat 100 % Wall-luokaksi).
- **Toimituspaksuus-snap vain ±12 mm sisältä**: 215 mm mitattu seinä EI ole
  200 mm — pakkosnap vei pinnan 9.5 mm pieleen. Kauempana standardista
  mitattu arvo jää toimitusarvoksi.
- **Pinnaton seinä flägätään**: jos seinäkaistassa on massaa muttei pintaa
  (MAD > 20 mm — telineet/tavara), confidence puolitetaan → QA nostaa
  "TARKISTA MANUAALISESTI" -listalle (ennen 46 mm fiktioseinä meni läpi
  ilman varoitusta).
- **run_floors lataa nyt 5 mm refine-pilven**: pintalukitus, trim, linjaus
  ja QA mittaavat samaa raakadataa (12 mm voxelin sentroidi-bias pois).
- **Perimetriseinän linjauskorjaus max 90 mm** (mitatuilla 25 mm):
  lattiakontuurigrid (25 mm ruutu + dilaatio) tuottaa kymmenien mm biasta —
  49 mm pielessä ollut perimetriseinä nyt 0.26 mm.
- **Perimetri-id:t uniikit** monikontuuritilanteessa (kaksi eri seinää oli
  molemmat wall_ext_001).

### Robustisuus mielivaltaisille skanneille (sama julkaisu)
Moniosaisella GT-talolla (000035, 8 skannia / 2 asuntoa) pipeline tuhosi
9/17 seinää → 0 tilaa. Viisi juurisyytä korjattu; nyt 14 seinää, 2 tilaa
(GT: 2), pintamediaani 0.11 mm (13/14 ≤ 1.5 mm). GT-asunnon tarkkuus
ennallaan (6/6 ≤ 1.5 mm, mediaani 0.10 mm) ja +2 aiemmin kadonnutta seinää.
- **Trim-romahdus**: risteävän seinän pisteet ±30 mm kaistassa romahduttivat
  datattoman seinän risteyskohtaan (4.0 m → 79 mm) → kutistus max 300 mm/pää.
- **Nurkkasulku-romahdus**: kaksi eri paria veti saman seinän molemmat päät
  samaan leikkauspisteeseen (2.8 m → 0 mm) → sulku saa kutistaa max 300 mm
  (syvempi leikkaus = T-liitos, ei nurkka).
- **Dedup söi pitkän seinän**: lyhyt korkean confidencen fragmentti syrjäytti
  koko seinän (2.2 m pätkä voitti 6.8 m perimetrin; 1.1 m pysty voitti 3.4 m
  vinon) → pisin jänne voittaa (lateraali korjataan pintalukituksessa).
- **Dangling-poisto söi oikean seinän**: pää jonka jatke yltää toiseen seinään
  (≤2.3 m, close_open_corners yhdistää sen) ei ole enää "irrallinen".
- **Vain suurin lattiakontuuri käsiteltiin**: paksun seinän takainen erillinen
  huone ei koskaan saanut perimetriseiniä → kaikki ≥1.5 m² lattia-alueet
  perimetrilähteiksi (`detect_floor_contours`).

## v0.5.2 — pintatarkkuus millitasolle + syötevahti
- **Seinäpinnat ≤0.2 mm skannatusta pinnasta** (oli 2–4 mm; GT-asunnolla mitattu
  0.00–0.18 mm): yksipuolisetkin seinät saavat raakapiste-pintalukituksen,
  lopullinen linjaus tehdään koko korkeuden pintamediaaniin (sama estimaattori
  kuin QA-mittari) ja nurkat suljetaan linjoja säilyttäen (T-liitosprojektio
  ei enää kallista lukittuja seiniä ~5 mm).
- **Toimituspaksuus ankkuroituna**: standardipaksuuteen snäppäys pitää skannatun
  pinnan paikallaan (ennen molemmat pinnat siirtyivät ±(std−mitattu)/2).
- **Aukkojen reunatarkennus**: ovi/ikkunareunat + silli/ylitys step-sovituksella
  raakapisteistä (30 mm gridin kvantisointi pois; ovi lattiatasoon sill<5 mm).
- **QA-raportti erottelee pintavirheen kohinasta**: uusi Pintatarkkuus-osio
  (pistetason hajonta sisältää skannerin kohinan 2–20 mm — pintamediaani ei).
- **Syötevahti**: varoitus kun yhdistetyt skannit eivät jaa pintoja keskenään
  (eri kohteita samassa ajossa) tai pilvi hajoaa erillisiin alueisiin.
- **Deterministinen**: PointNet-näytteistys siemennetty — sama syöte antaa
  saman mallin joka ajolla (ennen ±6 mm heittoa).
- Tunnettu puute kirjattu: korkeasokkeliset (>~600 mm) ikkunat eivät vielä
  löydy sarakedetektiolla.

## v0.5.1 — seinä- ja aukkotarkkuus (SpatialLM-GT-validointi)
- **Katto histogrammin reunabinistä**: `find_peaks` ei tunnista pilven ylintä
  tasoa (viimeinen bin) piikiksi → katoksi valikoitui alempi rakenne (−500 mm
  huonekorkeutta). Korjaus: histogrammin reunapehmustus + parikävely vain
  vertailukelpoiseen piikkiin (alakatto/kotelo/kaapinpäällys ei enää nappaa).
- **Kalustevarjot eivät enää tuota valeseiniä**: sängyn/sohvan varjolovi
  lattiakontuurissa hylätään perimetriseinänä jos katto jatkuu reunan
  ulkopuolella. Poisti huoneen halki risteilevät valeseinät.
- **`remove_dangling_walls` ei poista pitkiä seiniä** (≥2.5 m): aito detektoitu
  seinä jonka naapurit jäivät vajaiksi säilyy (nurkkien sulku yhdistää sen);
  aiemmin oikea yläseinä katosi ja tilalle jäi kaapiston etupinta (−525 mm).
- **Aidosti vinot seinät** (ei-Manhattan, 3–8°): uusi skew-polku
  (`orthogonal.refine_skew_walls`) palauttaa `regularize_orthogonal`in
  pakottaman kulman PCA-sovituksella + pintaverifioinnilla. GT-vertailussa
  vino ulkoseinä 5.7° → 0.3°, ja sen 2 m ikkuna löytyy nyt.
- **Aukkoluokittelu**: ovi vaatii lattiatason sokkelin (<250 mm, oli 500) ja
  saa olla 1800 mm leveä (pari-/liukuovi, oli 1500). Korkeasokkelinen aukko on
  ikkuna, leveä lattiatason aukko huoneiden välillä on ovi.
- Nolla-/jäämäseinät (<300 mm trim/snap-romahdus) siivotaan mallista.
- Uudet testit: `test_slab_detector.py`, `test_perimeter.py`,
  `test_orthogonal.py`, `test_wall_semantics.py`.

## v0.5.0 — kalustesuodatin (PointNet, Vaihe 2)
- **Uusi: ML-pohjainen kalustesuodatin** (`segmentation/pointnet_filter.py`).
  S3DIS PointNet ONNX-malli (CPU, ~3.4 MB) luokittelee jokaisen pisteen 13
  luokkaan ja poistaa kalusteet/krääsän (pöytä/tuoli/sohva/kaappi/taulu/clutter)
  ennen geometrista putkea. Rakenne (seinä/lattia/katto/pilari/palkki/ovi/ikkuna)
  säilyy. Malli bundlataan exe:hen — ei internetiä, ei GPU:ta.
- GUI: uusi "Kalustesuodatus (PointNet)" -kytkin (aktiivinen kun malli mukana).
- Pipeline: `PipelineConfig.semantic_filter_mode` = off|geometric|pointnet.
  Vanha geometrinen pystymaski säilyy fallbackina; PointNet toimii sen lisänä.
- Malli harjoitettu 3DSES TLS-skannidatalla (~20M pistettä), validointi:
  98.9 % rakenne säilyy, 48 % kalusteista poistuu. Vienti- ja harjoitusskripti:
  `scripts/export_s3dis_model.py`.

## v0.4.11
- Sulje vajaat ulkonurkat turvallisesti (`close_open_corners` pass-3): venytä
  avoin pää + kohtisuora kumppani nurkkaan vain jos venytysmatka on tyhjä → ei
  gridiä. Avoimet päät 4 → 1.

## v0.4.10
- `merge_collinear_walls`: yhdistä saman seinän jaetut pätkät yhdeksi (ohuempi
  paksuus) → poisti 300 mm pöhö-artefaktit. Paksuudet vain [66/92/120/200].

## v0.4.9
- `close_open_corners` (pass 1–2): yhdistä avoimet päät pareittain / kohtisuoraan
  olemassa olevaan seinään ilman gridiä. Vasen huone sulkeutuu.

## v0.4.8 — älykäs IFC
- IFC4: **tyypit** (`IfcWallType`/`DoorType`/`WindowType`/`SlabType`/`CoveringType`)
  + `RelDefinesByType`, **materiaalit** + `IfcMaterialLayerSet`, **Pset_*Common**
  (IsExternal/LoadBearing), **Qto-määrät**, järkevät nimet (VS/KVS/US + mm).
  Katto `IfcCovering CEILING`, tilat nimettyinä → muokattava Revit/ArchiCAD.
- Toimituspaksuus snäpätään rakennusstandardiin (7 tyyppiä, oli 14); tarkka
  mitattu arvo → `measured_thickness` + IFC `scan2bim_Mittaus`-pset.
- Lopullinen dedup poistaa päällekkäiset valeseinät (pitää ohuemman).

## v0.4.7 — kalustesuodatus + korkeus
- **Monikerros-pystymaski** (`wall_contour::_vertical_mask`): osakorkuiset
  kalusteet putoavat → ei valeseiniä. Paksuus 1.2 → 0.7 mm (80 % <1.5 mm).
- Sub-bin-laattataso: korkeusvirhe 167 → 4 mm (katto 0.3 mm).

## v0.4.4–v0.4.6 — paksuus- ja nurkkatarkkuus
- Raakapiste-paksuuslukitus (sub-bin): seinän paksuusvirhe 33.5 → 2.6 mm.
- `fine_rotate` sovittaa molemmat pinnat (keskilinja) → paksuus säilyy.
- Corner-resolve: seinät trimmataan/jatketaan todellisiin risteyksiin.
- Tarkkuusmittarit + vision-työkalut (`data/_*_qa.py`, `_overlay_prod.py`).

## v0.4.0–v0.4.3 — pintatarkkuus
- Pintalukitus: mallin pinnat skannatuille pinnoille (bias 61 → ~3 mm).
- Validoitu QA-mittari (`deviation.py`), ajetaan tuotantoajosta.

## v0.3.x
- **Contour-detektori defaultiksi** (Cloud2BIM-tyyli) + GUI plan view +
  perimetri/huone/ortogonaali-semantiikka.
- Ovidetektio (column-pohjainen), oikeat `IfcDoor`/`IfcWindow` aukkoihin.
- Itsepäivitys per-user-asennuksella (ei admin-oikeuksia).
- Pilaridetektorin DBSCAN-harvennus (esti OOMin hienolla pilvellä).

## v0.1–v0.2
- Perusputki: lataus → segmentointi → IFC4/DXF. PySide6-GUI + CLI +
  PyInstaller-jakelu. Schema-pohjainen arkkitehtuuri (StructuralModel).

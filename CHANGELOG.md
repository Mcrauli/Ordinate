# Muutosloki

Versiointi: `vMAJOR.MINOR.PATCH`. Releaset julkaistaan
[`Mcrauli/scan2bim-web`](https://github.com/Mcrauli/scan2bim-web/releases):iin;
sovellus päivittää itsensä sieltä.

## v0.9.8 (5.8.2026) — asennuksen ja itsepäivityksen kestävyys

- **Itsepäivitys ei voi enää muuttaa sovellusta asennusohjelmaksi.** Harvinaisessa
  tilanteessa päivitys saattoi napata asennusohjelman (Setup.exe) päivityspakettina ja
  korvata sovelluksen sillä — jolloin sovelluksen käynnistys avasikin asennusohjelman.
  Nyt päivitys hyväksyy vain varsinaisen ohjelmapaketin (zip); "Setup"-nimistä tiedostoa
  ei koskaan valita.
- **Uuden version asennus sulkee käynnissä olevan sovelluksen** ensin, sen sijaan että
  kaatuisi virheeseen "tiedosto on toisen prosessin käytössä" (Windows-virhe 32).
- 131 testiä läpi.

## v0.9.7 (5.8.2026) — liiketilan hyllyvaleseinät pois myös koko seinän mittaisina

- **Koko seinän mittainen lattia-katto-hylly poistetaan nyt valeseinänä.** Aiempi
  hyllynpoisto vaati, että hyllyn takana oleva seinä on selvästi pidempi — mutta
  perimetriä vasten koko matkalta kulkeva hylly on yhtä pitkä kuin seinä, joten se
  jäi jäljelle valeseinäksi. Uusi tunnistus: seinä on hyllyn etupinta, jos sen
  ULKOPUOLELLA (rakennuksen reunaa kohti) kulkee pitkä rinnakkainen perimetriseinä
  300–1500 mm päässä. **Mitattu** synteettisellä 48×32 m myymälällä: hyllyvaleseinät
  2 → 0, jäljelle jää tasan oikeat seinät (9/9), 13/13 pilaria, 0 ylimääräistä — ja
  ilman raskasta kalustesuodatinta. Vain liiketiloille (asunnoissa aito seinä voi
  olla lähellä ulkoseinää → niiden tulos ei muutu). 130 testiä läpi.

## v0.9.6 (5.8.2026) — liiketilan seinädetektio: deterministinen ja pilarivapaa

- **Uusi histogrammipohjainen seinädetektori liiketiloihin.** Aiempi RANSAC-
  detektori antoi saman skannin eri ajoilla eri seinämäärän (satunnaisuutta ei
  saanut vakioitua hidastamatta), oli hidas isossa pilvessä, ja sen kallistuneet
  tasot sekoittivat pilaririvit seiniin (valeseiniä ja ylivenymää). Uusi detektori
  löytää seinät suoraan pisteiden tiheyshuipuista rakennuksen pääsuunnissa: se on
  **toistettava (deterministinen), noin 130× nopeampi ja pilarivapaa** (pilari ei
  muodosta seinäviivaa). Se tunnistaa myös seinän molemmat pinnat, joten paksuus
  saadaan suoraan. **Mitattu** synteettisellä 48×32 m myymälällä: 9/9 seinää,
  13/13 pilaria, **0 valeseinää** (RANSAC: 8–9/9, 4–13 pilaria, 2–5 valeseinää ja
  luvut heittelivät ajojen välillä). Skaalautuu: 96×64 m (47 M pistettä) 1,6 s.
- Detektori valitaan automaattisesti vain liiketiloille (iso + korkea, suora-
  kulmainen). Asunnot ja tavalliset rakennukset (joissa voi olla vinoja seiniä)
  käyttävät entistä kontuuridetektoria — niiden tulos ei muutu. `--detector
  histogram` pakottaa uuden detektorin. 126 testiä läpi.

## v0.9.5 (5.8.2026) — iso myymälä: takahuoneen seinät löytyvät + vähemmän ylivenymää

- **Takahuoneen väliseinät löytyvät nyt (recall 6/9 → 9/9).** Isossa myymälässä
  aidot sisäseinät jäivät löytymättä, koska seinän luottamus laskettiin sen koon
  suhteessa koko pilveen — 12 m takahuoneen seinä on murto-osa 1500 m² hallista →
  luottamus romahti → seinä hylättiin. Lisätty kokoriippumaton **peitto** (kuinka
  tiheästi seinä on katettu pituudeltaan): aito seinä on lähes yhtäjaksoisesti
  katettu, hajanainen taso ei. Seinä säilytetään jos se on hyvin katettu, vaikka
  kokosuhteinen luottamus jäisi matalaksi. **Mitattu** synteettisellä 48×32 m
  myymälällä: takahuoneen seinät 6/9 → 9/9, hyllyvaleseiniä 0.
- **Seinät eivät enää veny tilan syvyyden yli lattialaatan takia.** Seinän pään
  paikka mitattiin koko korkeudelta, jolloin saman pystylinjan lattia- ja
  kattolaatta (pisteitä joka kohdassa) sai seinän näyttämään jatkuvan koko tilan
  läpi. Pää mitataan nyt keskikorkeudelta (vain seinäpinta). **Mitattu:** yli-
  venyneistä takahuoneen pystyseinistä 2/3 leikkautuu oikein.
- Asunto- ja talomallit ennallaan (käyttävät eri detektoria); 122 testiä läpi.

## v0.9.4 (4.8.2026) — iso myymälä: seinien ylitys pois + kalustesuodatin auto

- **Seinät eivät enää työnny rakennuksen ulkopuolelle.** Isossa liiketilassa
  seinän akseli saattoi venyä 9–31 m rakennuksen ulkopuolelle tyhjän lattian yli
  (päätepisteen leikkaus oli rajattu 300 mm:iin, jottei datattoman seinän kaista
  romahda risteyskohtaan). Nyt iso leikkaus sallitaan kun kaista on kiistatta aito
  seinäpinta (pitkä + tiheä), lyhyt/harva kaista säilyttää suojauksen. **Mitattu**
  synteettisellä 96×64 m myymälällä: seinät 5/9 → 7/9, pilarit 51/65 → 65/65,
  ei yhtään seinää rakennuksen ulkopuolella.
- **Kalustesuodatin kytkeytyy automaattisesti liiketilassa.** Lattiasta kattoon
  ulottuva myymälähylly seinää vasten on geometrisesti seinä, eikä koko seinän
  mittaista hyllyä voi erottaa aidosta seinästä pelkällä geometrialla. Semanttinen
  suodatin (PointNet) poistaa sen. Se kytketään nyt automaattisesti vain kun skene
  on iso ja korkea (pohja ≥ 600 m², vapaa korkeus ≥ 4,5 m = big-box-liiketila);
  asunnot ja tavalliset rakennukset (matala kerroskorkeus) eivät suodatu eivätkä
  hidastu. **Mitattu:** retail hylly-valeseinät 2 → 0, pilarit 20/20; asunto ja
  talo ennallaan (9 seinää / 3 ja 2 huonetta). Ohitus: `--semantic-filter
  auto|off|pointnet`.

## v0.9.3 (4.8.2026) — liiketilan hyllyn valeseinät pois
- **Lattia-katto-hyllykön etupintaan syntyneet valeseinät poistetaan.** Myymälän
  hyllykön etupinta ulottuu lattiasta kattoon, joten se on geometrisesti seinä
  eikä kalustesuodatin poista sitä (tiheä pystytaso) — arkkitehti sai pitkiä
  valeseiniä hyllyrivien eteen (mitattu synteettisellä myymälällä: 2 valeseinää,
  43 m). Uusi geometrinen erotin tunnistaa ne: hyllyn etupinta on lyhyehkö seinä
  joka kulkee rinnakkain ja 300–1500 mm irti paljon pidemmästä perimetriseinästä,
  jonka edessä se seisoo. Aito perimetriseinä on itse pisin eikä sillä ole
  pidempää rinnakkaista. **Mitattu:** retail hylly-valeseinät 2 → 0, ja kaikki 9
  GT-seinää löytyivät edelleen; asunto (7 seinää) ja talo (13) ennallaan.

## v0.9.2 (3.8.2026) — lisenssipuhtaat painot (3DSES pois); parempi rakenne
- **Semanttisen suodattimen malli koulutettu uudelleen ilman 3DSES:ää →
  lisenssipuhdas.** Aiemmat painot sisälsivät 3DSES-dataa (CC BY-SA 4.0), jonka
  ShareAlike-ulottuvuus mallin painoihin oli oikeudellisesti epäselvä — este
  kaupalliselle myynnille. Uusi malli on koulutettu pelkästään Rohbau3D:llä (MIT)
  ja omalla synteettisellä datalla (liiketila + monikerros + kalustetut huoneet),
  tyhjästä ilman esiharjoitettua checkpointia. **CC BY-SA -riski poistettu.**
- **Rakenteen säilyvyys parani samalla:** rohbau held-out -rakenne **0.947 →
  0.987** (mitattu), ja talo-END löysi yhden oikean perimetriseinän lisää.
  Asunnon ja talon loppumalli (seinät, tilat) on ekvivalentti aiempaan.
  Ainoa pieni kompromissi: asunnon sisäseinien pintatarkkuus ≤2.5 mm (aiemmin
  ≤1.5 mm) — synteettinen kaluste ei tavoita 3DSES:n oikean kalusteen tarkkuutta,
  mutta ero on skannerikohinan (20 mm) sisällä ja täyttää 1.5 mm -lupauksen
  useimmilla seinillä.
- **Lisenssiauditointi täydennetty:** kolmannen osapuolen ilmoitukset kattavat nyt
  myös Open3D:n transitiiviset riippuvuudet (Flask/Werkzeug/plotly ym.).

## v0.9.1 (3.8.2026) — one-dir-siirtymärelease; pilarit 34/34; suodatin kevyemmäksi
- **One-dir-paketointi käyttäjille (LGPL).** Sovellus toimitetaan nyt
  hakemistona (zip) yhden exen sijaan, jotta LGPL-kirjastot (IfcOpenShell, Qt)
  ovat vaihdettavissa. Itsepäivitys lataa zipin ja vaihtaa asennushakemiston
  tiedosto kerrallaan — yhä hiljainen, ei UAC:ia. **Siirtymä:** tämä release
  kantaa sekä zipin (uusi itsepäivitys) että Setup-asentajan; vanhat v0.8.x-
  asennukset päivittyvät Setupin kautta (kertaluontoinen UAC-kysely), sen jälkeen
  hiljainen zip-polku. Kolmannen osapuolen lisenssit toimitetaan mukana
  (THIRD-PARTY-NOTICES.md).
- **Pilarit 24/34 → 34/34 liiketilassa, ilman yhtään väärää positiivista.**
  Puuttuvat kaatuivat kaikki täsmälleen yhteen porttiin: `_waist_isolated` laski
  montako 24 kulmasektorista on täynnä vyötärökorkeudella (raja 4). Mittari oli
  väärä, ei kynnys — myymälässä gondoli seisoo pilarin molemmin puolin, jolloin
  **aito pilari peittää 16 sektoria eli yhtä monta kuin hylättävä tavaran
  ympäröimä kaappi**. Portti korvattu kahdella mitatulla ehdolla:
  1. suurin yhtenäinen **vapaa kaari** ≥45° (aito 60°/360°, kaappi 30°), ja
  2. **irtiolo seinästä** ≥250 mm — pelkkä kaari päästi läpi seinän mutkat,
     joilla huonepuoli on auki 180° (mitattu asunnosta: kolme valetta väleillä
     −123/−40/+104 mm, myymälän aidot pilarit ≥5420 mm).
  Todennettu viidellä datalla, sekä kattavuus että tarkkuus paranivat:
  | data | ennen | jälkeen |
  |---|---|---|
  | myymälä 72×48 m (GT 34) | 24/34, 0 väärää | **34/34, 0 väärää** |
  | kauppakeskus 150×100 m (GT 174) | 94/174, **3 väärää** | **174/174, 0 väärää** |
  | asunto / apt2 / makuuhuone / autotalli | — | **bitilleen sama `model.json`** |
  | 3DSES | 0 pilaria | 0 pilaria |
  | Rohbau site_07 | 0 pilaria | 0 pilaria |
  Detektorin aika 6.98 s vs 6.96 s (ero nolla); hallin muu tulos ennallaan
  (37 seinää, 2 tilaa, 4 aukkoa, 13.1 GB). Kaksi uutta testiä: gondolien
  välinen pilari LÖYDETTÄVÄ, seinän paksunnos EI ole pilari; kumpikin kaatuu
  ilman vastaavaa porttia.

- **Semanttisen suodattimen muistihuippu alas — se määrää koko tuotteen katon.**
  Mitattu 150×100 m hallilla (32 M pistettä): ajo huippusi 15.9 GB:hen ja
  jokainen muu vaihe jäi ≤5.8 GB, eli yksi vaihe ratkaisi katon; sama vaihe oli
  51 % ajasta. Poistettu hukkaa, ei työtä: 30 mm ruudukkoavain lasketaan erissä
  (yhden rivin lauseke varasi neljä pilven kokoista float64-välivaihetta),
  kuolleet taulukot vapautetaan heti (`vkey`, `first`, lohkoruudukon apurit —
  1.25 GB istui inferenssisilmukan yli), `SemanticLabels` johdetaan jo lasketusta
  ruudukosta eikä laskemalla identtinen ruudukko toiseen kertaan koko pilvelle,
  piirrefunktioista poistettu ehdoton `.astype(np.float64)`-kopio, ja
  `thick_cloud`/`refine_cloud` ladataan vasta suodattimen jälkeen (ne eivät ole
  sen syötettä). **Mitattu: 50.3 min / 15.9 GB → 42.5 min / 13.1 GB.**
  Tulos ennallaan ja se on TARKISTETTU eikä päätelty: `data/_filter_equiv.py`
  hashaa suodattimen koko tuloksen, ja 8.2 M liiketilaskannilla pidetyt pisteet,
  labeliavaimet, labeliarvot ja per-piste-luokat täsmäävät vanhaan koodiin;
  asunto, apt2, makuuhuone ja autotalli tuottavat bitilleen saman `model.json`:n;
  hallin malli on sama (37 seinää, 97 pilaria, 2 tilaa, 4 aukkoa).
  **Yhä auki:** 13.1 GB ei jätä varaa 16 GB:n koneella. Suodattimen työjoukko on
  verrannollinen rakennuksen 30 mm voxelien määrään (hallissa 31 M), joten
  hukanpoisto ei vie pidemmälle — riippuvuuden katkaisisi vain suodattimen
  ajaminen XY-ruuduittain, mikä muuttaa tulosta ruutujen rajoilla ja vaatii oman
  GT-validointinsa.

## v0.9.0 (1.8.2026) — liiketila- ja mittakaavavalidointi; yksipuoliset seinät paikalleen
- **Yksipuolinen seinä ei enää jää kymmeniä millejä pinnastaan.** Viimeinen
  pintalinjaus (`_align_faces_to_surface_median`) MITTASI virheen oikein mutta
  jätti sen korjaamatta 25 mm cappiin. Cap olettaa akselin olevan jo ~oikein —
  se pätee kaksipuoliselle seinälle, jonka kaksi pintaa kiinnittävät akselin,
  mutta yksipuolisella mitään kiinnitystä ei ole. Cap nousee kaistan reunaan asti
  vain kun vastapinnalla on <10 % dominantin pisteistä JA dominantti puoli on yksi
  tiivis taso (≥80 % ±30 mm mediaanista); kaksipuolisella se pysyy 25 mm:ssä.
  **Mitattu (`_tol_heatmap` raakapilveä vasten):** makuuhuone 4.7 m seinä
  **68.5 → 2.5 mm**; synteettinen myymälä 72 m ja 21 m ulkoseinä **57.4 ja
  62.1 → 0.0 mm**, jolloin kaikki 24 seinää ovat ≤0.4 mm. Asunto, apt2 ja
  autotalli tuottavat bitilleen saman mallin kuin ennen.
- **Iso tila on tila.** Kaksi eri estettä:
  1. `room_detector` hylkäsi kaiken yli 90 m² ("koko asunnon ulkokehä") —
     asuntokoosta johdettu absoluuttinen raja. Ulkokehä tunnistetaan nyt siitä
     mikä se oikeasti on: polygonize palauttaa sen reiällisenä. Samalla
     korjaantui että `Space.boundary` rakennettiin `.exterior`-renkaasta → ala
     kirjautui 80 m² kun kasvon oikea ala oli 71 m².
  2. Seinärengas ei ylipäätään sulkeudu isossa tilassa: perimetri pirstoutuu
     (itäseinä 5 palana, suurin rako 5.3 m) → myyntialuetta ei ole olemassa
     kasvona jota suodattaa. Lattiakontuuri syötetään nyt `detect_rooms`:iin
     renkaana, reunat kohdistettuna vastaavien seinien keskilinjoille. Kontuuri
     saa vain TÄYDENTÄÄ: tilat lasketaan ensin pelkistä seinistä ja kontuurin
     kasvoista otetaan vain kattamattomat, korkeammalla rimalla (≥6 m²,
     ≥1.2 m). **Mitattu:** myymälä 3 tilaa / 302 m² → **5 tilaa / 3453 m²**
     (hallin ala 3456 m²), ja ovien luokitus 2 ovea + 3 ikkunaa → **5 ovea**
     (`reclassify_interior_windows` tarvitsee huoneen aukon molemmin puolin).
     Asunto, apt2, makuuhuone ja autotalli tuottavat bitilleen saman mallin.
- **Maskista luettua paksuutta ei oteta alle 4 × pikselikoon.** Yksipuolisen
  pinnan viivan kontuuri kiertää sen molemmilta puolilta ja reunat luettiin
  kahdeksi pinnaksi → 66–92 mm "paksuus" vaikka pintoja on yksi. Oikea arvo
  mitataan joka tapauksessa raakapisteistä.
- **Liiketilavalidointi**: `data/_synth_retail.py` generoi parametrisen big-box-
  myymälän tunnetulla pohjalla (pilarikenttä, palkisto, lasijulkisivu, taustatilat,
  gondolit ja lattia-katto-hyllyköt) → `data/_retail_qa.py` vertaa mallia siihen.
  Oma data ⇒ käytettävissä myös markkinointiin ilman lisenssiehtoja.
- **Mittakaava mitattu ensimmäistä kertaa** (`data/_scale_run.py`): 72×48 m /
  8.2 M pistettä = 11.6 min ja 8.7 GB; 150×100 m / 32 M pistettä = 65.3 min ja
  **16.4 GB**. Ei kaadu, mutta 16 GB kannettava ei riitä isoon kohteeseen.
  Avoimet puutteet isossa liiketilassa: ks. AGENTS.md "Tunnetut rajoitukset".
- **Geometriaketju 4× nopeampi** (`core/geometry/xy_index.py`). Profilointi
  osoitti että jokainen seinäkohtainen vaihe laski projektiot KOKO pistetaulukolle
  (`_trim_endpoints` 41 s, `_surface_lock_wall` 38 s, `_refine` 19 s …). Indeksi
  rakennetaan kerran per pilvi ja palauttaa ylijoukon kaistan pisteistä; kutsuja
  soveltaa saman ehdon, joten valikoituva joukko ja sen järjestys ovat identtiset.
  **Mitattu:** ketju 244 → 59 s, koko liiketila-ajo 11.6 → 8.5 min, ja malli
  bitilleen sama asunnolla, apt2:lla, makuuhuoneella ja autotallilla.
- `point_features.geometric` lohkotettu (naapurihaun transientti rajattu);
  tulos on testillä varmistetusti identtinen.

## v0.8.9 (30.7.2026) — huoneala ja perimetri kuntoon, valeseinät pois
- **Lattiakontuuri ei enää leikkaa itseään.** Kalusteiden keilausvarjot syövät
  ohueen lattiaviipaleeseen lahdet, ja suhteellinen `approxPolyDP`-epsilon
  romahdutti ne ristiin meneväksi siksakiksi (mitattu asunnolla: 25 kärkeä,
  36.9 m² kun ala on 58 m²). Silloin perimetrin ULOSPÄIN-normaali oli
  merkityksetön ja seiniä syntyi fiktiivisille reunoille — asuntomallissa
  **haamuseinä 600 mm rakennuksen ulkopuolella, 0 pistettä koko 3.4 m matkalla**.
  Nyt huoneala lasketaan lattian ja katon yhdisteestä (katossa ei ole kalusteita),
  reiät täytetään ja epsilon on absoluuttinen → 31 kärkeä, 57.7 m², validi.
- **Huoneala ei ylitä seinää.** Detektoidut seinät katkaisevat alueen, joten se ei
  vuoda oviaukoista ja lasin läpi naapuritilaan. Katto vain sulkee varjot: alueesta
  on oltava ≥20 % lattiapisteiden peitossa, muuten se on keilausvuoto eikä huone.
- **Perimetri per rako, ei koko reunalle.** Aiemmin reuna hylättiin kokonaan jos
  detektoitu seinä kattoi siitä 35 % — metrien raot jäivät auki eikä huone
  sulkeutunut. Nyt katetut jänteet vähennetään ja seinä luodaan vain aidoille
  raoille, **mitatulle keskilinjalle** projisoituna (kontuurin sijaintivirhe voi
  olla satoja mm; väärässä paikassa oleva perimetri kaappasi nurkkasnapin ja
  tappoi aidon seinän).
- **Paksuus ei paisu kalusteesta.** Yksipuolisella ulkoseinällä huoneen puolella
  oleva kaappi ~300 mm pinnasta tuotti toisen "pinnan" → 372 mm paksuus ja akseli
  puoli valepaksuutta huoneen sisään. Pari hylätään jos seinän rungossa on kattoa
  (katossa ei ole kalusteita) → asunnon ulkoseinä 372 → 200 mm.
- **Mitattu vaikutus** (4 dataa, tuotantoajo PointNet-suodattimella): asunto
  55.8 → 58.0 m² huoneita ja haamuseinä pois; harvennettu asunto 54.2 → 55.7 m²
  ja 4 → 5 huonetta; makuuhuone 0 → 1 huone; autohalli tyhjästä mallista
  perimetriin. Testejä 84 → 86.

## v0.8.8 (25.7.2026) — Konvertoi aina näkyvissä
- **Konvertoi-nappi kiinnitetty sivupalkin alalaitaan.** Aiemmin se jäi
  vieritysalueen alle piiloon; nyt asetukset vierivät ja Konvertoi (+ palaute)
  pysyvät aina näkyvissä alhaalla, isompana ja selkeämpänä. Nappi on aktiivinen
  vain kun pistepilvi on valittu.

## v0.8.7 (25.7.2026) — ammattimainen ulkoasu
- **Käyttöliittymän visuaalinen uudistus.** Selkeä sivupalkki-rakenne (oma tausta
  + reuna erottaa asetukset sisällöstä), siistit lime-valintaruudut checkmarkilla
  (ei enää emoji-vedokset), alleviivatut välilehdet, viimeistellyt syöttökentät ja
  napit (ensisijainen lime / toissijainen ääriviiva), hienovaraiset reunat ja
  syvyys, hiotut vierityspalkit ja työkaluvihjeet. Yhtenäinen, myyntikelpoinen ilme.

## v0.8.6 (25.7.2026) — maalaa-valinta, IFC-nappi pohjaan, kapea-ikkuna-korjaus
- **Maalaamalla valinta.** Vasen veto tyhjästä piirtää valintalaatikon ja valitsee
  kaikki sen sisään osuvat elementit kerralla → **Poista** poistaa ne yhdellä
  kertaa. Helpompi kuin tarkka klikkaus. Yksittäisklikkaus valitsee yhden;
  panorointi tapahtuu nyt keski- tai oikealla napilla vetämällä.
- **"Kirjoita IFC uudelleen" myös pohjanäkymässä.** Kun poistat elementtejä
  suoraan pohjasta, puhtaan IFC:n voi kirjoittaa alapalkin napista — ei tarvitse
  vaihtaa Tarkistus-välilehdelle.
- **Kapean ikkunan asettelu korjattu.** Pitkä CRS-nimi ja drop-alue venyttivät
  vasenta paneelia liikaa scroll-alueessa → sisältö ja checkmarkit leikkautuivat.
  Combot elidataan ja drop-alue rivittyy → paneeli mahtuu siististi.

## v0.8.5 (25.7.2026) — klikkaa & poista pohjakuvassa
- **Klikkaa mitä tahansa elementtiä pohjassa → poista.** Seinän, pilarin, palkin
  tai aukon voi valita suoraan pohjapiirroksesta (ei vain tarkistuslistasta):
  klikkaus korostaa sen ja näyttää valintapalkin (tyyppi + luottamus) jossa
  **Poista**. Näin myös korkean luottamuksen virhedetektiot (esim. valepilarit,
  joita confidence-flägäys ei nappaa) saa käsin pois ennen exporttia →
  **Kirjoita IFC uudelleen** tuottaa puhtaan mallin.

## v0.8.4 (25.7.2026) — tarkistus-kerros
- **Epävarmat elementit merkitään ja voi poistaa ennen exporttia.** Matalan
  luottamuksen elementit (esim. yksipuoliset ulkoseinät, heikot aukot) näkyvät
  pohjakuvassa punaisella tarkistusmerkinnällä, ja uusi **Tarkistus**-välilehti
  listaa ne. Klikkaa → korostuu pohjassa; **Poista** → pois mallista;
  **Kirjoita IFC uudelleen** → puhtaampi IFC arkkitehdille. Lunastaa "ei tarvitse
  korjata jälkikäteen" -lupauksen niiltä osin kuin luottamus paljastaa virheet.

## v0.8.3 (25.7.2026) — layout-korjaus + QA siistitty
- **Pohjapiirros näyttää nyt myös laatat, pilarit ja palkit.** Lattia-laatan
  footprint hienovaraisena katkoviivana, pilarit umpitäyttönä (poché)
  profiilin kokoisina, palkit katkoviivana (yläpuolinen rakenne). Ennen näkyi
  vain seinät/huoneet/aukot.
- **Vasen paneeli vierii pienessä ikkunassa.** Aiemmin asetukset puristuivat
  päällekkäin kun sovellusta pienensi; nyt paneeli on scroll-alueessa ja
  ylimenevä osa vierii siististi.
- **Tarkkuusraportin mm-säädin poistettu.** Toleranssi oli vain raportin
  läpäisyrima (montako % pisteistä ≤ X mm mallin pinnasta) — se ei koskaan
  vaikuta itse malliin. Kiinteä 2.5 mm, ja rasti nimetty "Tarkkuusraportti"
  selittävällä työkaluvihjeellä.

## v0.8.2 (25.7.2026) — selkeämpi käyttöliittymä
- **Tulosfooter + "Avaa IFC" / "Avaa kansio".** Konversion jälkeen näkyy
  yhteenveto (seinät, huoneet + pinta-ala, ovet, ikkunat) ja painikkeet jotka
  avaavat IFC:n suoraan (Revit/ArchiCAD/Solibri) tai tuloskansion — ei tarvitse
  etsiä tiedostoa käsin resurssienhallinnasta.
- **Vaihekohtainen edistyminen.** Pyörivän spinnerin tilalle vaiherivi
  (Lataus → Esikäsittely → Suodatus → Detektio → IFC) joka syttyy ajon edetessä
  → pitkä ajo ei tunnu jumilta, näkee missä mennään.
- **Pohjapiirros-esikatselu näyttää oikealta pohjakuvalta.** Ovet piirretään
  aukkona + avautumiskaarena ja ikkunat aukkona + lasilinjana (ennen pelkkä
  piste), lisäksi hienovarainen 1 m -taustaruudukko, mittajana ja huoneiden
  pinta-alachipit. Aiempi köyhä "viivat + pisteet" -näkymä korvattu.
- **Voxel-koko-kenttä siistitty.** Manuaalinen syöttö on piilossa kun
  "Automaattinen" on valittuna (oletus) — ilmestyy vain jos auto otetaan pois.
  Auto valitsee koon datasta (pieni tila 8 mm → iso talo 25 mm), joten
  useimpien ei tarvitse koskea siihen.
- **DXF-export poistettu käyttöliittymästä.** Pääkäyttö on IFC (Revit /
  ArchiCAD), joten sovellus tuottaa vain IFC:n. DXF-export-koodi jää repoon
  (CLI/config voi yhä käyttää), mutta se ei ole enää oletusvalintana tiellä.

## v0.8.1 (24.7.2026) — ulkoskanni-robustius + nopeampi suodatin
- **Rakennusvaippa-rajaus.** Ulkoskannit (maasto, piha, ulkoklutteri) räjäyttivät
  aiemmin footprintin ja maanpinta voitti lattiapiikin → roskamalli. Nyt katon
  2D-peitto = rakennuksen vaippa, ja sen ulkopuoliset pisteet karsitaan ennen
  kontuuria. Mitattu synteettisellä ulko+rakennus-scenellä: footprint 16 m → oikea
  6 m, lattia −150 mm → 0, 4 jättivaleseinää → 0. Deterministinen, EI vaikuta
  sisätiladataan (asunto-GT bitilleen sama) eikä avoimeen työmaarunkoon (rajaus
  vain jos ≥10 % on katteetonta ulkoaluetta). Ulkoseinien paksuus mitataan silti
  niiden ulkopinnasta (thick_cloud rajaamaton).
- **Semanttinen suodatin ~1.85× nopeampi.** ONNX-inferenssi ajettiin lohko
  kerrallaan (batch=1) → iso skanni teki tuhansia erillisiä kutsuja. Batchaus
  (64 lohkoa/kutsu) + kaikki ytimet: suodatinvaihe 73.6 s → 39.7 s (10.9 M
  pisteen skene). Ulostulo bitilleen sama (verifioitu: säilyttää tarkalleen
  saman pistemäärän ennen ja jälkeen).

## v0.8.0 (23.7.2026) — uusi semanttinen kalustesuodatin (hyllyt, monikorkeus)
- **Vaihe 2: semanttinen suodatin uusittu.** Per-piste-segmentointimalli
  (`models/s3dis_pointnet*.onnx`) korvattu geometria- ja pystyjatkuvuuspiirteillä
  vahvistetulla PointNet-mallilla, joka on koulutettu myös synteettisillä
  liiketila- ja monikorkeusskeneillä. Poistaa kalusteet, krääsän JA liiketilojen
  lattia-katto-hyllyt ennen geometrista putkea — geometrinen pystymaski ei niitä
  nähnyt. XYZ-only (ei väririippuvuutta), CPU-ONNX, yhtä nopea kuin ennen (27 ms/lohko).
- **Toimii vaihtuvilla korkeuksilla.** Pystyjatkuvuuspiirteet normalisoidaan
  paikallisen sarakelattian ja kiinteän 3 m kerroksen suhteen → korkea market-katto,
  välipalkit ja eri korkuiset huoneet eivät enää sekoita suodatinta (palkit 71→96 %,
  portaat 83→93 % rohbau-työmaan monikerrosskenessä).
- **Mitattu (koko pipeline GT:tä vasten):** asunto seinän lateraali 82→62 mm
  (p90 246→169 mm), talo35 109→105 mm ja kulma 1.68→1.30°, rohbau rakenne-säily
  0.879→0.947. Puhtaampi pilvi → nurkka- ja kulmaviimeistely osuu paremmin.

## v0.7.10 (16.7.2026) — adaptiivinen voxel, rehellinen QA-loki, vähemmän valepilareita
- **Auto-voxel toimii oikeasti.** Aiemmin tuotantopolku kovakoodasi 12 mm ja
  tulosti harhaanjohtavasti "Auto-voxel". Nyt kevyt 20 mm-otos ensimmäisen
  kerroksen kaistasta valitsee voxelikoon datasta: pieni huone → 8 mm (tarkempi,
  löytää oviakin), iso talo → 25 mm (muistiturvallinen). Mitattu: pintatarkkuus
  parani ja aukkoja löytyi enemmän.
- **QA-loki näyttää oikean luvun.** Ennen loki näytti pistetason "% ≤ 2.5 mm"
  joka on skannerin kohinan (20–27 mm RMS) dominoima → pelotti turhaan. Nyt loki
  näyttää **mallin pintatarkkuuden** (mediaani mm + montako seinää ≤1.5 mm) ja
  kohinan erikseen kontekstina.
- **Vähemmän valepilareita sotkuisissa skanneissa.** Seinänpätkät, skannerin
  asemapiste-"donitsit" ja vuotorajan roska menivät pilareiksi. Kaksi mitattua,
  deterministista lisäsuodatinta: (1) **sektoripeitto** — aidon vapaan pilarin
  ympärillä on avointa lattiaa (0–1 kulmasektoria täynnä vyötärökorkeudella),
  massaan kiinni oleva vale 6–9 → hylätään; (2) **min-leveys 200 mm** — ohuet
  donitsi­artefaktit pois (aidot pilarit ≥240 mm). Mitattu 3DSES-huoneilla:
  valepilarit 3–4 → 1, valepalkki 1 → 0. Aidot pilarit säilyvät.

## v0.7.9 (15.7.2026) — IFC-georeferointi (koordinaatisto-leima)
- **IFC saa georef-leiman (`IfcProjectedCRS` + `IfcMapConversion`).** Malli
  kirjoitetaan kuten ennenkin skannin OIKEISIIN maailmakoordinaatteihin (iso
  itä/pohjoinen + korkeus) → overlay pistepilveä vasten (Cintoo tms.) osuu
  täsmälleen. Leima kertoo lisäksi minkä koordinaatiston koordinaateista on kyse,
  jotta Revit/Navisworks osaa sijoittaa mallin shared/survey-koordinaateilla
  eikä valita etäisyydestä origoon. **Geometria ei muutu** — mitään ei siirretä.
- **Koordinaatisto valittavissa** (GUI: "Koordinaatisto"; asetus `crs_epsg`).
  Oletus **ETRS-TM35FIN (EPSG:3067)**, lisäksi ETRS-GK19…GK31 (mm. GK25 pää-
  kaupunkiseutu), KKJ/YKJ, sekä "Ei georef-leimaa". Oikean järjestelmän saa
  yleensä skannin/E57:n headerista.
- Yksikkö hoidettu oikein: geometria mm, projisoitu CRS metreissä → skaalaus
  mm→m, offset 0 (geometria kantaa jo täyden koordinaatin).

## v0.7.8 (15.7.2026) — vähemmän valepilareita ja -palkkeja sotkuisissa skanneissa
- **Täyskorkea kaluste ei enää mene pilariksi eikä kalusteen päällä oleva klusteri
  palkiksi.** Huonoissa/kalustetuissa skanneissa (esim. skannerivuoto aukon läpi)
  detektorit poimivat sälää: 3DSES-huoneesta tuli 3 valepilaria + 1 valepalkki
  saman vuotorajan rykelmästä. Kolme mitattua, deterministista tiukennusta:
  - **Pilari — poikkileikkauksen vakaus:** aidon pilarin XY-jalanjälki on ~sama
    joka korkeudella; kasattu kaluste heiluu (mitattu 35↔500 mm) → hylky.
  - **Pilari — vyötäröirrallisuus:** aidon pilarin ympäri kävelee (ilmaa 1–1.8 m
    korkeudella); täyskorkea kaappi on kiinni muussa massassa (mitattu: aito ≤4/16
    suuntaa täynnä, kaappi 8/16) → hylky.
  - **Palkki — headroom:** aidon palkin alta kävelee (tyhjää alla); kalustepatterin
    päällä istuva klusteri on tukossa → hylky (vain valmiissa tilassa).
  Mitattu S171-huoneella: pilarit 3→1, palkit 1→0. Aidot pilarit/palkit säilyvät
  (kaikki detektoritestit läpi, +3 regressiotestiä). Jäljelle jäävä täyskorkea,
  irrallinen, vakaa klusteri on geometrisesti aito pilari — sitä ei enää erota
  ilman semanttista tietoa.

## v0.7.7 (15.7.2026) — vähemmän valepalkkeja: roikkuva talotekniikka ei ole palkki
- **Valmiissa tilassa (kattolaatta löydetty) katosta irti roikkuva pitkänomainen
  klusteri ei enää mene palkiksi.** Aito alaslaskettu palkki valetaan kattolaatan
  kanssa yhteen → sen kyljet ulottuvat kattoon asti; ripustettu talotekniikka
  (putket, kanavat, kaapelihyllyt) roikkuu katosta irti. Nyt vaaditaan että
  klusterin lakipiste yltää katon alapintaan (soffit-kiinnitys, ≤130 mm) tai
  klusteri hylätään. Lisäksi valmiissa tilassa alle 150 mm leveä kattoon
  kiinnittynyt klusteri = putki/kouru, ei palkki. Tämä poistaa valepalkit
  MEP-täyteisissä liike- ja toimistotiloissa. Työmaalla (ei kattolaattaa) testi
  ei ole voimassa → aidot palkit säilyvät. Vision-varmennettu Matterportilla:
  valepalkit 12 → 8/10.

## v0.7.6 (12.7.2026) — puskuliitokset: seinät eivät enää limity nurkissa
- **IFC-seinäsolidit eivät enää mene sisäkkäin liitoksissa.** Akselit päättyvät
  leikkauspisteeseen → molempien seinien suorakaiteet peittivät nurkkaneliön
  (5–9 cm sisäkkäin joka nurkassa) ja ulkonurkkaan jäi kolo. Nyt L-nurkassa
  paksumpi seinä jatkuu läpi toisen ulkopintaan ja toinen katkaistaan sen
  sisäpintaan; T-liitoksessa pystyseinä katkaistaan läpimenevän pintaan.
  Koskee vain IFC-solidia — akselit, mittaukset ja QA eivät muutu.
  Mitattu Matterport-aulalla: limitykset 24.7/21.1/55.2/15.1 cm² → 0.3/0.1 cm²
  (jäännös vinokulmista, ~0.5 mm — ei näy). Vision-varmennettu ennen/jälkeen.

## v0.7.5 (12.7.2026) — sisäkkäiset seinät korjattu + diagnostiikkanapin mailto-fix
- **Korjaus: perimetrijatke ei enää jää mitatun seinän kanssa sisäkkäin.**
  Sama fyysinen seinä jakautui mitattuun pätkään ja perimetri-täyteseinään,
  jotka olivat ~150 mm sivussa toisistaan (kontuurigrid-bias + 300 mm-swellin
  akselisiirto) → pinnat limittyivät nurkassa ja arkkitehti joutui korjaamaan.
  Perimetrijatke sulautetaan nyt MITATUN seinän linjalle (tarkempi akseli ja
  paksuus voittaa fiktioseinän). Todennettu Matterport-aulalla: 8→7 seinää,
  0 sisäkkäistä paria, yhdistetty seinä pinnassa 0.70 mm; pintamediaani 0.08 mm.
- **Korjaus: "Lähetä diagnostiikka" saattoi epäonnistua hiljaa.** Windowsin
  mailto-kytkös voi osoittaa poistettuun sovellukseen (vanha Windows Mail),
  jolloin mitään ei avaudu mutta sovellus väitti luonnoksen auenneen.
- Dialogi näyttää nyt aina vastaanottajan ja aiheen, ja tarjoaa kaksi
  avausnappia: **Avaa sähköpostiohjelma** (mailto) ja **Avaa Gmail selaimessa**
  (toimii vaikka mailto-kytkös on rikki). Molemmissa vastaanottaja, aihe ja
  palautepohja valmiina.

## v0.7.4 (10.7.2026) — diagnostiikan palautesilmukka
- **"Lähetä diagnostiikka kehittäjälle" -nappi:** niputtaa kaikkien ajojen
  diagnostiikan (versio, vaiheet, varoitukset, tulokset — EI geometriaa) yhdeksi
  tiedostoksi ja avaa esitäytetyn sähköpostiluonnoksen + palautepohjan. Asiakas
  liittää tiedoston ja lähettää. Ei backendiä, toimii rajoitetussa verkossa.
- **Rullaava diagnostiikkahistoria** (`%APPDATA%\scan2bim\`): joka ajo kertyy
  yhteen lokiin → näkyy mitä on ajettu ja missä meni pieleen, ilman skanneja.
  Tämä on pilotin tukikanava ja pilari/palkkimallin koulutusdatan lähde.

## v0.7.3 (9.7.2026) — palkit vain soffit-vyöhykkeeltä (ripustettu talotekniikka pois)
- **Palkkidetektio vain katon alapinnan SOFFIT-vyöhykkeeltä** (valmiissa tilassa
  jossa kattolaatta löytyy). Katosta 380–1600 mm alas roikkuva tavara on
  ripustettua talotekniikkaa (putket/kanavat/kaapelihyllyt/valaisimet), ei palkki.
  Vaikutus mitattu: liiketilan aula 32→12 palkkia. **Työmaa (ei kattolaattaa)
  säilyttää leveän kaistan** → aidot runkopalkit eivät katoa (Rohbau 5→5).
- Huom: hajonnut/talotekniikkatäyteinen skanni voi silti tuottaa palkkikohinaa
  (geometria ei erota kattotason kanavaa palkista); pipeline flägää epäluotettavat
  skannit ja matalan luottamuksen palkit erikseen.

## v0.7.2 (9.7.2026) — valepilarit/-palkit pois, aidot säilyvät
- **Pilari-muotosuhderajaus (≤2,5):** aidot pilarit ovat kompakteja (mitattu
  Rohbau-työmaa 1,1–2,3); pitkänomaiset "pilarit" (3,4–11) ovat detektoimattomia
  seinänpaloja tai keilausvarjon reunoja → pois. Pilarin luottamus heijastaa nyt
  kompaktiutta (ei enää satu 1,0:aan).
- **Palkin min-pituus 400→700 mm:** aidot palkit ovat pitkiä; lyhyet pätkät ovat
  kattoputkea/-krääsää.
- **QA flägää nyt myös pilarit (<0,45) ja palkit (<0,35)** matalalla luottamuksella
  → TARKISTA MANUAALISESTI -listalle, eivät esiinny varmoina.
- Todennettu (ennen→jälkeen): asunto 4+3→0+0, talo035 3+2→1+0, Rohbau-työmaa
  7+8→7+5 (kaikki 7 aitoa pilaria säilyi). Vision-varmennettu.

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

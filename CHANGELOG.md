# Muutosloki

Versiointi: `vMAJOR.MINOR.PATCH`. Releaset julkaistaan
[`Mcrauli/Ordinate-web`](https://github.com/Mcrauli/Ordinate-web/releases):iin;
sovellus päivittää itsensä sieltä.

## v0.9.36 (2.10.2026) — enemmän seiniä pienissä tiloissa, halleissa ja kellarissa

- **Paloina näkyvä seinä löytyy.** Isossa matalassa tilassa seinä, jonka
  putket ja laitteet katkovat moneen osaan, kootaan nyt yhdeksi seinäksi
  suoranhaulla (Hough) korkeiden solujen kartasta. Kellarissa 14 uutta seinää,
  36,3 / 38 m osuu pintaan; kattavuus 0.444 → 0.537, tarkkuus 0.214 → 0.226.
  Muut 11 aineistoa bitilleen ennallaan.
- **Isoissa halleissa löytyy enemmän väliseiniä.** Ohjelma käytti ennen vain
  yhden seinätunnistimen tulosta; nyt toisen tunnistimen löytämät seinät
  lisätään, jos ne ovat yhtenäistä pintaa eivätkä pilarin tai julkisivun
  ripoja. Runkovaiheen testikohteissa löydettyjen seinien osuus 54 % → 63 %
  (yksi scene 41 % → 59 %), tarkkuus ennallaan; myymälöissä ei muutosta.
- **Pienissä tiloissa verrataan valmiita malleja.** Ennen pieni tila meni aina
  yhdellä tunnistimella, ja jos se epäonnistui, malli jäi tyhjäksi (porraskäytävä
  0/26 seinää). Nyt ohjelma ajaa tarvittaessa kaksi vaihtoehtoa loppuun asti ja
  pitää paremman. 43 runkovaiheen keilauksessa löydetyt seinät 399 → 447 (+12 %),
  tarkkuus 0.868 → 0.856.
- **Opittu seinätarkistin pienissä tiloissa.** Ohjelma ajaa nyt kolme
  tunnistusketjua ja lisää malliin muiden ketjujen löytämät seinät, jos niille
  koulutettu tarkistin sanoo kyseessä olevan seinä eikä palkki-, pilari- tai
  porraslinja. Tarkistin on koulutettu 93 runkovaiheen keilauksella kuudelta
  työmaalta (Rohbau3D, CC BY 4.0). Löydetyt seinät 689 → 737 (+7 %), tarkkuus
  0.848 → 0.855; asunnossa ja synteettisessä kohteessa löytyy enemmän seiniä.
- Päivittäjä hakee julkaisut `Mcrauli/Ordinate-web`-reposta (vanha nimi
  ohjautuu GitHubissa, joten vanhat asennukset päivittyvät yhä).

## v0.9.35 (28.9.2026) — tuotenimi Ordinate, kellariin lisää seiniä

- **Isoissa matalissa tiloissa löytyy enemmän seiniä.** Putkien ja laitteiden
  keskeltä kulkeva seinä jäi ennen löytämättä, koska se sulautui ympäröivään
  sotkuun. Kellarikohteessa löytyi 12 uutta seinää, eikä yksikään vanha
  muuttunut; muut testikohteet ennallaan.
- **scan2bim on nyt Ordinate.** Ikkuna, asennusohjelma, pikakuvakkeet, exe
  (`Ordinate.exe`, komentorivi `ordinate-cli.exe`), IFC-tiedoston ohjelmatieto ja
  mittauspset (`Ordinate_Mittaus`, ent. `scan2bim_Mittaus`).
- **Päivitys toimii vanhasta versiosta suoraan:** sovelluskansiossa on vielä
  `scan2bim.exe`, jotta vanha itsepäivitys löytää sen; vanhat pikakuvakkeet
  korvataan Ordinate-pikakuvakkeilla. Diagnostiikkahistoria alkaa alusta
  `%APPDATA%\Ordinate`-kansioon.

## v0.9.34 (18.9.2026) — ovet ja ikkunat löytyvät useammin ja oikeaan kohtaan

- **Aukon korkeus ja reunat mitataan raakapilvestä.** Reunojen hienosäätö
  luki 25 mm:iin harvennettua pilveä, jolloin ikkunan yläreuna meni
  keskimäärin 99 mm pieleen. Nyt korkeuden mediaanivirhe on 14 mm.
- **Ovi löytyy myös kun seinä katkeaa sen kohdalta kahdeksi pätkäksi.**
  Ovi hyväksytään vain, jos sen päällä on ylitys ja seinä jatkuu raon
  molemmin puolin; seinä jatketaan raon yli.
- **Ikkuna ei enää katoa, jos seinän alin reuna on keilautunut vajaasti.**
- Mitattu: keilattu myymälä 5 → 8 aukkoa kymmenestä (väärät 1 → 1), Rohbau
  19 → 25 GT-aukkoa ilman tarkkuuden laskua. Seinät ennallaan kaikilla 12
  vertailuaineistolla.

## v0.9.33 (17.9.2026) — kellari 39 → 25 min, malli bitilleen sama

- **Iso kohde valmistuu kolmanneksen nopeammin, eikä tulos muutu.** Mitattu
  koulun kellarilla (37 skannia koneen NVMe:ltä): **2334 s → 1502 s**, ja
  seinät, laatat, pilarit, palkit, aukot ja tilat ovat JSONina täsmälleen
  samat. Matriisi: kaikki 12 aineistoa +0.000, Rohbaun GT-luvut ennallaan.
  - **Skannit puretaan kolme kertaa, ei kuutta.** Paksuuskaista ja 5 mm
    -pilvi lukivat samat tiedostot peräkkäin kahdella passilla kumpikin; nyt
    ne syntyvät samasta purusta. Voxelivalinta ja työpilvi syntyvät nekin
    samasta purusta, joten isossa kohteessa työpilvi on valmis heti.
  - **Pilaridetektio 110.7 s → 1.1 s.** Etäisyys laskettiin jokaisesta
    pisteestä jokaiseen seinään, vaikka päätös tarvitsee vain lähimmät.
  - **Aukkojen okkluusiotesti 11 s → noin sekunti per ehdokas.** Säde voi
    osua aukkoon vain aseman ja aukon välisestä kolmiosta, ja ensimmäinen
    läpi näkevä asema ratkaisee.
  Jokainen muutos on todistettu samaksi erikseen (SHA1 tai sama päätös joka
  pisteelle) ennen koko ajoa.

## v0.9.32 (17.9.2026) — 3D-näkymä toimii myös toisen ajon jälkeen

- **3D-tarkastus näytti tyhjää, kun edellä oli tarkasteltu toista kohdetta.**
  Pilvi latautui oikein, mutta uuden pilven latauksessa asetettiin vain kameran
  etäisyys. Lentotila siirtää katseen keskipistettä, joten kamera katsoi yhä
  sinne missä edellinen rakennus oli: toistettuna 36 m sivuun ja 80° ylöspäin.
  Nyt keskipiste ja katsekulma nollataan jokaiselle uudelle pilvelle.
- Kaatuneiden istuntojen 3D-välitiedostot (18–108 MB kpl) siivotaan
  käynnistyksessä.

## v0.9.31 (17.9.2026) — 3D-tarkastus ei enää kaadu, ajon kesto näkyy

- **3D-tarkastus kaatui yhä pilveä ladatessa — 0.9.30:n korjaus oli väärä.**
  Loki näytti kolmannen kaatumisen rivillä `res[:, 0] = 0.95`, eli
  kirjoituksessa taulukkoon joka oli varattu edellisellä rivillä. Sellainen
  kaatuu vain jos prosessin muisti on jo rikki, joten funktion uudelleen-
  kirjoitus ei voinut auttaa. Kaikissa kolmessa kaatumisessa 1.5 M pisteen
  pilvi oli juuri ladattu näytönohjaimelle samalla kun taustasäie laski
  numpyllä. Nyt ikkunaprosessi ei tee pilvelle mitään laskentaa eikä aja
  yhtään taustasäiettä: pisteet, värit, residuaali ja "vain puuttuvat"
  lasketaan valmiiksi aliprosessissa. Seinän poiston jälkeen residuaali
  lasketaan uudelleen samoista pisteistä lukematta skanneja uudestaan.
  Mitattu päästä päähän: ikkunan pisin tauko 0.08 s.
- **Ajon kesto näkyy.** Tilarivillä juokseva kello ja nykyinen vaihe;
  lopuksi kokonaisaika ja kolme pisintä vaihetta lokiin.

## v0.9.30 (16.9.2026) — 3D-tarkastuksen kaatuminen korjattu, varoitus hitaasta levystä

- **3D-tarkastus kaatoi sovelluksen.** Loki nimesi sen vihdoin: muistin
  suojausvirhe `numpy.tile`-kutsussa residuaalivärien rakennuksessa. Väritaulu
  varataan nyt suoraan, pisteiden ja värien määrät tarkistetaan sen sijaan
  että indeksoitaisiin taulukon yli, eikä koko pilveä ladata enää turhaan
  näytönohjaimelle väri-moodissa — juuri siinä kohdassa sovellus kuoli.
- **Putki varoittaa hitaasta syötelevystä.** Mitattu samalla 37 skannin
  kellarilla: **USB-tikulta 56 min, koneen omalta NVMe:ltä 39 min**, tulos
  bitilleen sama. Putki lukee skannit neljä kertaa, joten tikulla 26 minuuttia
  ajosta on pelkkää levyn odottamista. Ajo mittaa nyt syötelevyn nopeuden alle
  sekunnissa ja kertoo sen.

## v0.9.29 (16.9.2026) — kaatumisesta jää jälki, eikä virhe enää tapa ikkunaa

- **Virhe toiminnossa ei enää sulje sovellusta.** PySide6 tappaa prosessin
  `abort()`illa kun Python-poikkeus jää käsittelemättä slotissa — ikkuna vain
  katoaa. Kaikki 35 käyttäjän toimintoa (tarkistuslista, pohjan valinta,
  3D-tarkastus, IFC:n uudelleenkirjoitus) on nyt suojattu: virhe kirjataan
  lokiin, näkyy ilmoituksena ja sovellus jatkaa. Ilmoitus on ei-modaali,
  koska modaali dialogi olisi itsessään uusi jäätymä.

## v0.9.28 (16.9.2026) — kaatumisesta jää vihdoin jälki

- **Sovellus kaatui kahdesti eikä lokiin jäänyt riviäkään.** Syy oli lokissa
  itsessään: `sys.stderr` ohjattiin tiedostoon Pythonin tasolla, mutta
  PySide6 tappaa prosessin `abort()`illa kun Python-poikkeus jää
  käsittelemättä slotissa, ja se jälki menee **C-tason stderriin (fd 2)** —
  joka ikkunasovelluksessa ei osoita mihinkään. Nyt fd 1 ja 2 ohjataan
  `os.dup2`:lla lokitiedostoon, `faulthandler` on päällä ja käsittelemätön
  poikkeus kirjataan aikaleimalla sekä pää- että taustasäikeistä.
  Loki: `%TEMP%\scan2bim_gui.log`, ja siihen kirjataan myös versio ja
  käynnistysaika, jotta rivit osaa yhdistää oikeaan ajoon.
  Molemmat kaatumiset (0xc0000409, ucrtbase) tapahtuivat pääsäikeessä Qt:n
  tapahtumasilmukassa — itse vika on vielä selvittämättä, ja tämä on se
  muutos jolla se saadaan näkyviin.

## v0.9.27 (16.9.2026) — ei enää jäätymistä, skannien luku 1.7× nopeampi

- **"Näytä pistepilvi" jäädytti koko sovelluksen — myös pohjanäkymän.**
  Pilvi ladattiin taustasäikeessä, mutta e57-lukija ei vapauta GIL:iä:
  mitattu yhdellä 834 MB tiedostolla, toinen säie seisoi **4.2 s**. 36
  skannia jäädytti ikkunan viideksi minuutiksi, ja samalla kaikki muukin —
  siitä "ei vastaa" ja hitaus IFC:n jälkeen. Lataus ajetaan nyt omassa
  prosessissaan: mitattu kuudella kellarin skannilla **92 s → 25 s**, ja
  ikkunan pisin tauko koko latauksen aikana **70 ms**. Lataus näyttää
  edistymisen tiedostoittain ja sen voi peruuttaa.
- **Skannit luetaan rinnakkain.** Neljä kellarin e57:ää: 2 prosessia 1.53×,
  4 prosessia **2.24×**, 6 ei enää parane (levy rajoittaa). Tulos on
  bitilleen sama — todistettu SHA1-tarkistussummalla työpilvelle,
  täysresoluutiokaistalle ja 5 mm pilvelle.
- **Mitattu koko ajo, koulun kellari 37 skannia (31.7 GB): 66 min → 56 min.**
  Tiedostojen luku (neljä kierrosta) 2607 s → **1541 s**. Loppuaika on nyt
  PointNet-suodattimessa (591 s) ja semantiikkaketjussa — ne ovat seuraavat
  kohteet, lukua nopeuttamalla ei enää saada paljoa.
- Matriisi: kaikki 12 aineistoa +0.000.

## v0.9.25 (14.9.2026) — Tarkistus oppii korjauksistasi

- **Tarkistus käy nyt koko mallin läpi ja järjestää seinät sen mukaan mitä
  tässä rakennuksessa on opittu.** Hyväksy aito seinä tai poista väärä, ja
  lista siirtyy suoraan seuraavaan. 20 päätöksen jälkeen sovellus oppii
  päätöksistäsi mikä erottaa valeseinän aidosta juuri tässä kohteessa ja
  nostaa epäilyttävimmät kärkeen. Mitään ei poisteta automaattisesti.
  Mitattu koulun kellarilla (28 valeseinää, käyttäjän omat labelit, 30
  arvontaa): **40 tarkistuksella löytyy 22 valeseinää, kun vanhalla listalla
  5.8** — ja se vanha lista oli kellarissa vain kaksi seinää pitkä.
  Korjaukset tallentuvat tuloskansioon (`corrections.json`) ja säilyvät kun
  mallin avaa uudelleen. Opittu ei siirry toiseen rakennukseen (mitattu),
  joten jokainen projekti aloittaa alusta.
- **Tarkistus on pohjakuvan vieressä eikä omana välilehtenä**, joten
  valittu seinä näkyy korostettuna koko ajan.
- **Listalla ei näytetä epäilyprosenttia.** Järjestys on mitatusti oikea,
  mutta mallin todennäköisyys ei ole: kellarissa 10 epäilyttävimmästä viisi
  oli valeseiniä samalla kun luku väitti keskimäärin 6 %.
- Putki mittaa jokaiselle seinälle kymmenen pilvipiirrettä
  (`Wall.evidence`), 5 s kellarissa. Todistettu bitilleen samaksi kuin
  mittauskoetin kaikilla 244 seinällä. Geometria ennallaan: matriisi
  kaikilla 12 aineistolla +0.000.

## v0.9.24 (10.9.2026) — kaksoisid:t pois, paketti todistaa GUI:n ajopolun

- **Sama seinä-id kahdesti samassa mallissa.** Putki ajaa jäännösseinähaun
  kahdesti (geometriaketjun sisällä ja sen jälkeen) ja kumpikin ajo numeroi
  nollasta, joten koulun kellarin mallissa oli `wall_res_000…008` **kahteen
  kertaan**. Duplikaatti-id sekoittaa IFC:n, QA:n ja jokaisen työkalun joka
  viittaa seinään id:llä — se löytyi labeloinnista, jossa kaksi eri seinää
  näytti samalta riviltä. Numerointi jatkuu nyt mallissa jo olevista id:istä
  (`tests/test_residual_ids.py`, varmistettu mutatoimalla). Matriisi:
  **kaikki 12 aineistoa +0.000**, Rohbaun GT-instanssit +0.000 — korjaus ei
  liikuta geometriaa.

- **Savutesti todistaa nyt myös sen että GUI löytää komentorivin.**
  `cli_command()`:n `sys.frozen`-haara — se joka etsii `scan2bim-cli.exe`n
  GUI-exen vierestä — ei aja kehityksessä koskaan, eli se on täsmälleen sitä
  lajia joka toimii venvissä ja hajoaa asiakkaalla. Paketista ajetaan nyt
  `scan2bim-cli.exe selftest-paths`, joka ratkaisee polun samalla koodilla
  kuin GUI ja vaatii että molemmat exet ovat olemassa.

## v0.9.23 (10.9.2026) — sovellus ei enää jäädy

- **Putki ajetaan nyt ERILLISENÄ PROSESSINA, ei säikeenä.** `ProcessWorker` oli
  `QThread` joka ajoi `Pipeline.run_floors()`:n samassa prosessissa. Putken
  semantiikkaketju on täynnä puhdasta Python-silmukkaa, joka pitää GIL:iä →
  Qt:n tapahtumasilmukka ei päässyt ajoon ja ikkuna jäätyi kesken ajon
  ("ei vastaa"). Nyt GUI käynnistää paketin oman `scan2bim-cli.exe run`
  -komennon `QProcess`illa ja lukee vain sen stdoutin; tulokset luetaan
  levyltä (`floor_NN/model.json`). Mitattu offscreen-ajossa: koko putkiajon
  aikana UI-säikeen pisin tauko **78 ms** (ennen: koko ajon mittainen).
  Tämä on myös se syy miksi komentorivi kuuluu pakettiin — GUI on nyt sen
  ensimmäinen käyttäjä, ja `scripts/smoke_exe.py` ajaa `run`-komennon
  pakatusta tuotteesta ennen zippausta.

- **3D-tarkastus jäätyi pistepilveä avattaessa.** Kolme syytä, kaikki
  UI-säikeellä: pistebudjetti oli 6 M, `_rgba`/`_pts`-taulukot rakennettiin
  vasta latauksen jälkeen pääsäikeessä, ja **residuaaliluokittelu ajoi 219
  seinää × 6 M pistettä** ennen kuin mitään piirtyi — mitattu **34.4 s**
  pelkkää luokittelua UI-säikeellä. Nyt budjetti on 1.5 M,
  taulukot rakennetaan lataussäikeessä ja luokittelu ajetaan omassa
  säikeessään — näkymä piirtyy heti ja väritys päivittyy kun laskenta
  valmistuu. Lisäksi `_stop_thread` kutsui `QThread.wait()`ia pääsäikeestä
  ilman aikarajaa; teardown on nyt ei-blokkaava. Mitattu kellarin 219 seinän
  mallilla: lataus 9.6 s + luokittelu 8.8 s, **UI-säikeen pisin tauko 130 ms**.

## v0.9.22 (10.9.2026) — putki 36 % nopeampi, komentorivi pakettiin, kadonneet seinät takaisin

- **Komentorivi puuttui paketista kokonaan — nyt mukana `scan2bim-cli.exe`.**
  Julkaistava exe rakentuu GUI:sta ja on `console=False`, joten
  `scan2bim.exe convert …` vain avasi ikkunan: eräajo tai skriptaus ei ollut
  mahdollista millään koneella. CLI rakentuu nyt samasta `Analysis`:sta, eli
  siinä on täsmälleen samat riippuvuudet ja sama malli — ei toista latausta
  eikä versioeroa. Käyttö: `scan2bim-cli.exe convert <pilvi> <ulos>`.

- **Kolme muuta pakettivikaa, kaikki sellaisia jotka toimivat kehityksessä ja
  hajosivat asiakkaalla.** (1) Spec pakkasi semanttisen suodattimen mallin
  ehdolla, joten ilman mallia exe kääntyi normaalisti ja putki putosi
  **hiljaa** geometriseen fallbackiin — build keskeytyy nyt virheeseen.
  (2) `cli.py`:stä puuttui `__main__`-vartija; se toimi vain `pip install -e`:n
  luoman käynnistimen kautta ja päättyi muuten koodilla 0 tekemättä mitään.
  (3) `--help` kaatoi CLI:n `UnicodeEncodeError`iin cp1252-konsolissa, koska
  suomenkielisessä tekstissä on `→`; tulostus pakotetaan nyt UTF-8:aan.
  Suojaksi `scripts/smoke_exe.py` ajetaan osana buildia **ennen zippausta**:
  se kopioi paketin repon ulkopuolelle ja ajaa siellä oikean konversion, joten
  asennuspaketti ja itsepäivitys perivät saman takuun.

- **Kadonneet seinät: hyllynpoisto tuomitsi muodosta.** `remove_shelf_front_walls`
  poisti seinän joka on lyhyehkö, rinnakkainen ja 300–1500 mm päässä paljon
  pidemmästä — mutta runkovaiheen rakennuksessa se muoto on aito kipsiseinä
  julkisivun edessä. Poisto vaatii nyt todisteen: seinän vieressä on oltava
  vaakatasoja (mitattu erottelu — Rohbaun GT-seinät 0–2 tasoa, myymälän
  hyllynetupinnat 7–9). Mitattu: asunto kattavuus **0.681 → 0.813** ja seiniä
  9 → 13, Rohbau 07003 GT-instanssit 0.556 → 0.593, kellari 0.366 → 0.379;
  myymälät ennallaan 9/9 GT-seinällä ja nollalla hyllyvaleseinällä.

- **Seinien pirstoutuminen: 660 mm kuollut vyöhyke kahden säännön välissä.**
  `merge_collinear_walls` hyväksyi railon ≤450 mm ja `bridge_lintel_gaps`
  300–2200 mm mutta vain ≤25 mm kohtisuoralla erolla, joten 660 mm railo
  130 mm sivussa ei kuulunut kummallekaan. Railo saa nyt olla pidempi jos sen
  kohdalla ON seinäpintaa, katto 800 mm = kapein oviaukko. Mitattu
  liiketilassa: **36 seinäoliota → 13**, GT-seiniä löytyi 7/9 → **9/9**,
  ylimääräisiä 29 → 4.


- **Detektorivalinta ei enää palkitse MÄÄRÄSTÄ.** `_best_detector` valitsi
  detektorin `wall_coverage`lla, joka on puhdas recall: jokainen lisätty seinä
  voi vain nostaa sitä eikä yksikään väärä laske sitä. Mitattu seuraus: kun
  histogrammidetektorin piikkikynnystä löysättiin (aito korjaus lyhyille
  seinille), se voitti kellarin valintakisan kattavuudella 0.103 ja vei
  lopputuloksen 0.366 → 0.203 (240 → 123 seinää), retail_l:n 37 → 10.
  Nyt valinta tehdään kattavuuden ja tarkkuuden F1:llä (`wall_scores`,
  `detector_score`), sama määritelmä kuin matriisin mittarissa.
  Matriisi: kaikki 12 aineistoa **+0.000** — voittaja ei vaihdu yhdelläkään,
  mutta kaappausmekanismi on poissa.

- **Nopeus: toimituspaksuuden ankkurointi indeksoitu ja pistevälin KD-puu
  nopeampi.** `_snap_delivery_thickness` skannasi koko pilven jokaista seinää
  kohti (32 s). `_nn_spacing` rakensi tasapainotetun KD-puun 24 M pisteelle
  kysyäkseen 20 000 pisteen naapurit, kuudesti ajossa (31 s);
  `balanced_tree=False, compact_nodes=False` rakentaa 2× nopeammin ja kysely on
  yhä tarkka — etäisyydet mitattu **bitilleen identtisiksi**. Matriisi: kaikki
  12 aineistoa +0.000, kellari 658 → 610 s. Session alusta: kellari
  1455 → 610 s (−58 %), matriisi 5981 → 3714 s (−38 %).

- **Nopeus, jatkoa: aukkodetektio, katkaisu, kate ja jäännöksen lunastus
  indeksoitu.** Samat neljä kohtaa skannasivat koko pilven jokaista seinää
  kohti. Kaksi kohtaa vaati erikoiskohtelun jotta tulos pysyy samana:
  `_wall_openings` valitsee mitattavan pinnan KOKO tasokaistalta, joten siinä
  saa rajata vain kohtisuoraan; `split_gaps`:n ohuen kaistan varasääntö
  lasketaan lajitellusta z:stä koko pilvestä, ei osajoukosta.
  Matriisi: kaikki 12 aineistoa **+0.000**, yhteisaika 4142 s → 3811 s;
  kellari 854 → 658 s. Session alusta: 5981 → 3811 s (−36 %), kellari −55 %.

- **Nopeus: koko putki 31 % nopeampi, malli bitilleen sama.** Profiloitu
  (`data/_prof_run.py`) koulun kellarilla — kaksi kuviota söi puolet ajosta:
  `fine_rotate_walls` + `refine_skew_walls` skannasivat KOKO 45 M pilven
  jokaista seinää kohti (544 kutsua, 337 s), ja sama pilvi indeksoitiin
  ketjussa **22 kertaa** (188 s pelkkää argsortia). Nyt kiertopassit hakevat
  pisteet kaistaindeksistä ja indeksi on pilvikohtaisessa välimuistissa.
  Matriisi: kaikki 12 aineistoa **+0.000** (kattavuus, tarkkuus, seinät, aukot,
  GT), yhteisaika 5981 s → 4142 s; kellari 1455 → 854 s, retail_l 2248 → 1676 s.

- **Nurkkakoneisto ohitetaan isossa matalassa tilassa** — mitattu koulun
  kellarilla: `regularize_orthogonal` + `snap_corners` + `close_open_corners` +
  `merge_collinear_walls` identiteetteinä antaa **kattavuuden 0.194 → 0.366**,
  kontrastin 27 → 69, ja korjaa samalla paksuusvirheen −84 → **−14 mm** (sama
  juurisyy: snäppäys siirtää akselin pois pinnalta ja paksuuslukitus mittaa
  väärän piikkiparin). Reititys: ala ≥ 600 m² JA vapaa korkeus < 3.5 m.
  Matriisi: kaikki yksitoista muuta aineistoa bitilleen ennallaan.

- **KORJATTU: sovellus ei ajanut semanttista suodatinta koulun kellarilla
  lainkaan.** `auto`-tila vaati sekä 600 m² että 4.5 m korkeutta; kellari on
  7137 m² mutta matala, joten suodatin — ja sen mukana semanttinen karsinta,
  joka poistaa 119 seinää — ei koskaan lauennut tuotannossa. Matriisi ei
  paljastanut tätä, koska `_run_one.py` pakottaa `pointnet`-tilan. Nyt `auto`
  kytkee suodattimen myös pelkän alan perusteella. Todennettu: kellarin malli
  `auto`-tilassa on bitilleen sama kuin pakotetulla `pointnet`illa.
- **Nopeus: siirtyneiden seinien napsautus indeksoitu.** Se skannasi koko
  24.5 M pilven jokaista ehdokasta kohti — kellarilla 239 s (18 % ajosta) siihen
  että yksi seinä siirtyi. Malli bitilleen sama kolmella aineistolla.

- **Jäännösseinähaku ajetaan kahdesti — ja se on missä puuttuvat seinät olivat.**
  Ennen karsintaa mallissa on vielä kaikki valeseinät, ja ne LUNASTAVAT juuri
  sen pinnan josta puuttuvat seinät löytyisivät: samasta pilvestä haku antaa
  siinä kohdassa 9 seinää, puhdistetusta mallista **49**. Pelkkä siirto
  myöhemmäksi ei kelvannut (liiketila-L 0.695 → 0.622, Rohbau 07003 GT
  0.849 → 0.831), joten haku ajetaan molemmissa kohdissa ja uudet ehdokkaat
  käyvät kolme todisteporttia uudelleen. Portit tuomitsevat vain UUDET seinät:
  kontrastiportin voimaehto on suhteessa mallin omaan mediaanitiheyteen, ja
  49 uutta seinää siirtäisi sitä niin että vanhoja tuomittaisiin uudelleen
  (mitattu: ilman suojaa scene_07003 GT 0.849 → 0.829).
  **Kellari 66 → 110 seinää, kattavuus 0.141 → 0.194, tarkkuus 0.249 → 0.265;
  synteettinen 0.785 → 0.802; Rohbau 07000 GT 0.915 → 0.920 ja 07001
  0.903 → 0.905. Ei yhtään regressiota.**

- **Uusi portti: onko seinän suunnassa pintaa** (`semantics/direction_prune.py`).
  Kellarissa 58 % mallin seinäpituudesta kulki suuntaan jota pilvi ei tue, ja
  ne olivat juuri ne pitkät vinot valeseinät jotka läpäisivät kaikki muut
  portit. Mittari on pilven oma normaalihistogrammi. Matriisi: **kaikki
  yksitoista muuta aineistoa bitilleen ennallaan**, kellari 101 → 66 seinää ja
  tarkkuus 0.207 → **0.249**.

- **Jäännösseinähaku kytketty takaisin** — sama moduuli joka kytkettiin pois
  18.8., mutta nyt ketjussa on kolme mitattua porttia jotka osaavat tuomita
  ehdokkaat. **GT-kattavuus nousee kaikilla viidellä Rohbau-scenellä**
  (0.886 → 0.915, 0.863 → 0.903, 0.859 → 0.863, 0.824 → 0.849, 0.755 → 0.759)
  hintana 0.002–0.016 GT-tarkkuutta. Synteettinen 0.688 → **0.785**,
  liiketila-L 0.620 → **0.695**, kellari 0.177 → 0.191 ja sen tarkkuus
  0.202 → 0.207. Asunto, liiketila-S, test_room ja 3DSES eivät menetä
  kattavuutta.

- **Uusi portti: onko seinän kaistassa TASO** (`semantics/flatness_prune.py`).
  Aito seinäpinta on taso (hajonta millejä); putki ja kanava täyttävät kaistan
  tasaisesti (kymmeniä millejä). Mitattu mediaanihajonta: liiketila 2.1 mm,
  asunto 4.2 mm, Rohbau 2.8–6.1 mm, synteettinen 14.6 mm, **koulun kellari
  28.7 mm**. Matriisi: Rohbau scene_07003 GT-tarkkuus **0.912 → 0.923**,
  3DSES **0.582 → 0.664**, asunto / liiketilat / test_room / synteettinen
  bitilleen ennallaan, kellari 101 → 93 seinää ja tarkkuus 0.194 → **0.202**.

- **Joka ajo kertoo nyt itse onko sen malli luotettava**
  (`core/qa/reliability.py`, diagnostiikkaan). Kolme suhdelukua joita skannin
  koko tai tiheys ei liikuta: seinän kontrasti ympäristöönsä, osuus seinistä
  oman pintansa päällä, ja mallin paksuus vs. pinnoista mitattu. Asunto ei saa
  yhtään varoitusta (14.15 / 100 % / −14 mm); kellari saa sen yhden joka on
  todella auki (paksuus −84 mm). Lisäkustannus 5 s.
- **Kellarin paksuus on mitatusti väärin (66 mm kun pinnat ovat 225 mm päässä),
  mutta korjaus "suosi vastakkaisen puolen pintaa" KUMOUTUI** — se paransi
  asuntoa (0.681 → 0.725) ja kellaria mutta vei Rohbau scene_07000:lta
  GT-kattavuutta 0.886 → 0.843 ja synteettiseltä 0.688 → 0.635. Ks. AGENTS.md.

- **Uusi portti: erottuuko seinä ympäristöstään** (`semantics/contrast_prune.py`).
  Kaikki aiemmat portit mittaavat TASOA — tukea, jatkuvuutta, katetta — ja taso
  riippuu skannista: matalassa talotekniikkakellarissa jokaisen linjan varrella
  on putki, joten `prune_unsupported_walls`:n kysymys "onko kaistassa pisteitä"
  on aina tosi (mitattu 396 seinästä: sarakekate p10 1.00, mediaani 1.00).
  Uusi portti kysyy suhteen: onko seinän kohdalla ENEMMÄN pystypintaa kuin
  0.75–1.25 m sen vierellä. Suhde on dimensioton eikä riipu keilaustiheydestä
  eikä huonekorkeudesta. Mitattu kontrasti: asunto min 1.87, liiketila 1.95,
  Rohbau 1.00, **kellari min 0.01 ja mediaani 1.00**.
  **Sokeusehto tekee siitä turvallisen:** 10 m hallissa aidon seinän molemmilla
  puolilla voi olla nolla seinämäistä pistettä, jolloin kontrasti on 1.00
  pelkästä nollasta. Portti tuomitsee vain siellä missä seinän ±3 m ympäristössä
  on pintaa vähintään 10 % mallin omasta mediaanista.
  Mitattu (sääntö ajettuna valmiille malleille): Rohbau viisi sceneä
  GT-kattavuus muuttumatta ja **07001:n GT-tarkkuus 0.864 → 0.957**; kellari
  125 → 61 seinää, tarkkuus 0.163 → **0.239**, kattavuus 0.233 → 0.228.
  Koko putken matriisi ajettu: **Rohbaun viisi sceneä GT-kattavuudeltaan
  muuttumattomia ja 07001:n GT-tarkkuus 0.864 → 0.957**, 3DSES-tarkkuus
  0.542 → 0.579, asunto / liiketilat / test_room bitilleen ennallaan,
  synteettinen 0.692 → 0.688. Kellari 160 → 101 seinää, tarkkuus
  0.150 → **0.194**, kattavuus 0.209 → 0.188.

- **Semanttinen karsinta on nyt ENEMMISTÖÄÄNI (0.30 → 0.50).** Seinä poistetaan
  kun sen pinnan luokitelluista pisteistä alle puolet on seinätasoa. Vanha 0.30
  päästi läpi kaiken minkä pinnalla oli edes kolmannes seinää, ja koulun
  kellarissa se on putkien ja kanavien normaalitila: mallin seinien seinäosuus
  on mediaanina 0.33. **Kellari 427 → 160 seinää, tarkkuus 0.089 → 0.150,
  kattavuus 0.334 → 0.209** — poistuva pituus on ristikkoa joka kulki pisteiden
  yli, ja sen mukana lähtee myös kattavuutta jota se lunasti sattumalta.
  Kynnys ei ole viritetty käyrältä: Rohbaun viisi sceneä antavat 0.50, 0.60 ja
  0.70 kynnyksillä **täsmälleen samat GT-luvut**, joten betonirungossa sääntö
  ei kosketa aitoja seiniä lainkaan.
- **Kehitysajan välimuisti semanttisille luokille** (`SCAN2BIM_SEM_CACHE_DIR`).
  PointNet on kellarilla 8 min ja jokainen semanttinen koe tarvitsee samat
  luokat samasta pilvestä. Pois päältä ilman ympäristömuuttujaa, joten
  tuotantopolku ei muutu.

- **Kerrosjako vaatii pintojen VÄLIIN betonin, ei pelkkää väliä.** Jako oli
  kiinni pisteiden tiheydessä: sama scene antoi 1 kerroksen pistevälillä 4, 10
  ja 70 mm mutta 2 kerrosta pistevälillä 17 ja 35 mm. Jakautuessaan palkit
  menivät kahteen kerrokseen ja `floor_00` jäi tyhjäksi — palkkikattavuus
  0.857, 0.929, **0.000**, **0.000**, 0.857 vaikka detektori yksin antoi 12/14
  joka tiheydellä; seinäkattavuus heitteli 0.327–0.490. Vanha sääntö tarkisti
  vain piikkiryhmän leveyden (100–600 mm); mitattu scene_07000 voxelilla 20:
  ryhmä z 5363..5563 on 200 mm leveä mutta sen sisällä ei ole yhtään tyhjää
  binia — yksi paksu pinta, ei kaksi. Nyt vaaditaan tyhjä kaista pintojen
  välissä, ja tyhjyys on osuus ryhmän omasta huipusta. **Tulos: 1 kerros joka
  tiheydellä, kaikilla viidellä scenellä.**

- **Palkkien kiinnitysportti poistettu — se mittasi näkyvyyttä, ei kiinnitystä.**
  Portti vaati, ettei alapinnan ja laatan välissä ole 300 mm tyhjää. Korkeassa
  tilassa lattialta keilattaessa palkin uuma on katsomissuunnan takana eikä sitä
  skannata lainkaan, joten portti hylkäsi aidon palkin siitä ettei sitä nähdä.
  Ablaatio kaikilla viidellä Rohbau-scenellä (pelkkä detektori): portti päällä
  39/77 tarkkuudella 0.824, pois **62/77** tarkkuudella 0.808 — 23 aitoa palkkia
  hinnaksi 0.016 tarkkuudesta. Liiketila-S, liiketila-L ja asunto antoivat
  täsmälleen saman tuloksen kummallakin. Hinta on tiedossa ja testattu:
  valmiissa tilassa roikkuva kanava tulee nyt palkiksi.
- **Alapinta luetaan solun alimmasta PINNASTA, ei alimmasta pisteestä.** Minimi
  on tiheysmittari: 200 mm solussa on 4 mm skannissa ~2500 pistettä ja 70 mm
  skannissa ~8, joten yksi harhapiste painaa alapinnan alas sitä varmemmin mitä
  tiheämpi skanni on — ja `z_free`n alle painunut solu poistetaan kartasta
  kokonaan. Pinta = alin taso jonka ympärille kertyy osuus solun omista
  pisteistä. Kattavuus 12/14 joka tiheydellä ennen ja jälkeen, tarkkuus
  0.838 → 0.866 (4 mm) … 0.882 → 0.911 (70 mm).
- **Palkin minimisyvyys skaalautuu huonekorkeudesta.** Kiinteä 150 mm on oikein
  2.7 m huoneessa ja väärin 10 m hallissa: se päästi läpi 460–1700 mm syvät
  kattorivat ja kanavat, joiden alapinta oli kaikkien GT-palkkien yläpuolella.
  Raja on nyt suurempi luvuista 150 mm ja 8 % vapaasta korkeudesta. Mitattu
  kuudella aineistolla: instanssikattavuus säilyi **täsmälleen samana**
  jokaisessa ja tarkkuus nousi 0.866→0.905, 0.738→0.799, 0.744→0.850,
  0.814→0.869, 0.876→0.877; liiketila ennallaan 1.000.
- **Yhteisvaikutus palkkeihin läpi putken: 31/77 → 59/77** (0.403 → 0.766),
  tarkkuus 0.877 / 0.818 / 0.851 / 0.932 / 0.859.

- **Yksikkötunnistus ei enää riipu rakennuksen koosta.** Sääntö oli "laajuus
  < 200 → metrit", joten 250 m halli metreissä jäi skaalaamatta ja koko putki
  mallinsi 250 mm rakennuksen ilman yhtään virhettä. Pisteväli erottaa yksiköt
  koosta riippumatta (mitattu: Rohbau metreissä 0.016–0.024, mm-pilvet 2–124).
  Sääntö oli neljänä kopiona — loader, PLY-luotain, E57-luotain ja `inspect`
  joka katsoi vain x-akselia; kaikki kutsuvat nyt samaa `metre_scale`ia.
- **Mittaamaton jatkuvuus ei ole todiste seinän tuesta.** Kolme vikaa samassa
  paikassa: `deviation.py` kaatui `None < float`-vertailuun heti kun tuki on
  hyvä mutta vyötäröllä ei ole pisteitä; karsinta päästi läpi juuri sen seinän
  jolla oli VÄHITEN evidenssiä; ja lyhyen seinän suoja oli ristiriidassa oman
  dokumentaationsa kanssa. Mitattu: ongelmaseiniä 7 → **4**, seinäinstanssit ja
  pistekattavuus täsmälleen ennallaan, tarkkuus 0.860 → 0.864 ja 0.927 → 0.928.
- **Aukkomittarin nimittäjä on fysikaalinen, ei pistemäärä.** `_opening_qa`
  ohitti alle 500 pisteen GT-instanssit, jolloin harvempi skanni pudottaa
  pienet aukot nimittäjästä ja kattavuus näyttää paremmalta ilman että mikään
  paranee. Nyt raja on 300 × 300 mm.

- **Aukon leveyskatto 2500 → 3000 mm.** Runkovaiheen oviaukot ovat 2.5–3.0 m ja
  jäivät kiinteään kattoon; suhteellinen katto (50 % seinän pituudesta) hoitaa
  varsinaisen rajauksen. Mitattu Rohbau3D:n GT:tä vasten: scene_07000
  5/35 → 6/35 ja tarkkuus 0.312 → 0.353, scene_07003 2/19 → 3/19 ja
  0.500 → 0.600, scene_07002 ennallaan. Asunto (4 aukkoa) ja liiketila
  (6 aukkoa) eivät muuttuneet.

- **Palkin syvyysraja skaalautuu tilan korkeudesta.** Kiinteä 3000 mm oli
  kiinni Rohbau site_07:n palkeissa (2.6 m), joten seuraavan hallin syvempi
  palkisto olisi pudonnut kokonaan. Raja on nyt suurempi luvuista 3000 mm ja
  35 % vapaasta korkeudesta. Mitatut luvut eivät muuttuneet (Rohbau 0.834 /
  8-14 ja 0.837 / 8-15, liiketila 0.856 / 1.000).
- **Vanhentuneet `floor_NN`-hakemistot poistetaan ajon alussa.** Kerrosjako voi
  muuttua ajojen välillä; vanha `floor_01` jäi levylle ja meni `building.ifc`:hen
  mukaan, jolloin malli sisälsi kerroksen jota nykyinen ajo ei tunnista.

- **Kerrosjako vaatii pintaparin, ei tiheintä vaakapintaa.** 10 m hallissa
  palkiston alapinta on tiheämpi kuin oikea katto (Rohbau scene_07001: 2.9 M vs
  2.8 M pistettä), joten `_split_tall_slice` keksi kerroksen palkiston kohdalle
  ja katkaisi palkit kesken. Aito kerrosjako on kaksi pintaa — alemman kerroksen
  katto ja ylemmän lattia (mitattu aidosta kaksikerroksisesta keilauksesta:
  3000 ja 3296 mm). Sisäinen laatta vaatii nyt parin 100–600 mm.
  Palkit: scene_07001 instanssikattavuus 0.21 → **0.42**, tarkkuus
  0.354 → **0.812**; kaikki scenet yhteensä 34/77 → **38/77**.
- **Pilarin korkeus ja alapää mitataan, ei oleteta.** Pystytäyttö lasketaan
  yhtenäisenä jaksona ja `base_z` tulee jaksosta; ennen se oli aina lattian
  taso riippumatta siitä missä jäsen oikeasti on.

- **Palkki mitataan alapinnasta, ei pisteklusterista.** Vanha detektori
  klusteroi kattokaistan pisteet XY:ssä ja luki palkin leveyden klusterin
  XY-laajuudesta. Skannattu palkki ei ole umpikappale vaan kaksi pystypintaa ja
  niiden välinen alapinta, joten klusterin leveys ei ollut palkin leveys:
  synteettisen liiketilan sama 300 mm palkki antoi joko 143 mm (yksi pinta
  erillisenä klusterina) tai 47 000 mm (koko palkisto ketjuuntui pilarien kautta
  yhdeksi klusteriksi), ja molemmat hylättiin leveysportissa.
  Uusi malli lukee jokaiselle 200 mm solulle kattokaistan alimman pisteen,
  yhdistää samankorkeat naapurisolut laikuksi ja mittaa leveyden laikusta.
  Mitattu Rohbau3D:n per-piste-GT:tä ja synteettisen liiketilan GT:tä vasten
  (`data/_beam_qa.py`, `data/_beam_synth_qa.py`):
  | mittari | ennen | jälkeen |
  |---|---|---|
  | Rohbau, GT-palkki-instansseja löydetty | 0/77 | **34/77** |
  | Rohbau, tarkkuus (scene_07000) | 0.048 | **0.834** |
  | liiketila, GT-palkin akselipituudesta katettu | 0.012 | **0.856** |
  | liiketila, harhapalkkeja | 0 | **0** |
  | asunto, hormi palkkina | 1 | **0** |
  Samat luvut koko putken läpi PointNet-suodattimen kanssa, eli suodatin ei
  syö alapintoja.
- **Asunnon hormi ei enää ole palkki, eikä siihen tarvittu omaa sääntöä.**
  Alapintaehto pudottaa kaikki lattiaan yltävät kappaleet — seinän, pilarin,
  hyllykön, gondolin ja hormin — koska niiden alin piste ei ole katon lähellä.
  Kolme aiemmin kokeiltua erikoissääntöä kumoutuivat mittauksessa; oikea
  korjaus oli vaihtaa malli.
- **Pilarien katkomat palkin pätkät yhdistetään yhdeksi jäseneksi**, mutta vain
  jos ne ovat samansuuntaisia, samalla alapinnalla ja väli on alle 1500 mm.
  Kauempana toisistaan olevat samansuuntaiset palkit jäävät erilleen, jottei
  synny samaa ylivenytystä joka seinäpuolelta jouduttiin leikkaamaan pois.
- **Palkkien mittarit** ovat uusia: `data/_beam_qa.py` (per-piste-GT + per-
  instanssikattavuus), `data/_beam_synth_qa.py` (synteettinen GT),
  `data/_soffit_sweep.py` (porttien valinta mitatusta välistä),
  `data/_beam_run.py` (pelkkä palkkidetektio valmiiseen malliin).
  `data/_synth_retail.py` kirjoittaa nyt myös palkiston GT:hen.

## v0.9.20 (17.8.2026) — evidenssin yli venytetty seinä leikataan pintaan

- **Evidenssin yli venytetty seinänpää leikataan takaisin pintaan.**
  `snap_corners` ja `close_open_corners` venyttävät akselin päitä pelkällä
  geometrisella rajalla (1300 mm / 2300 mm) eivätkä kysy onko venytetyllä
  osalla yhtään pistettä. Asuntoskannauksessa se näkyi näin
  (`data/_extent_qa.py`): wall_013 kate 0.78, 800 mm häntä ilmassa; wall_005
  kate 0.63, hännät 600 + 800 mm. Uusi `semantics/overstretch.py` leikkaa pään
  VAIN jos se on samaan aikaan kattamaton yli 700 mm:n matkalta JA yhä
  irrallaan (>60 mm kaikista muista seinistä). Ehto 2 tekee siitä turvallisen:
  venytys nurkkaan on laillinen mallinnusvara, mutta asunnossa nämä päät
  roikkuivat 542 mm ja 495 mm irti eli venytys ei ostanut mitään. Nurkkaan
  osuvaan päähän ei kosketa, joten suljettu nurkka ei voi avautua.
  Kattamaton KESKIOSA on oviaukko eikä sitä katsota.
  Asunto: wall_013 kate 0.78 → 1.00, pituus 3663 → 2863 mm.
- **Keksitty nurkka tunnistetaan vastinseinän katteesta.** Pelkkä irrallisuus ei
  riitä: kaksi kattamatonta häntää voi kohdata TOISENSA, jolloin kumpikaan pää ei
  ole irrallaan mutta nurkka lepää tyhjän päällä. Mitattu asunnosta: wall_002 ja
  wall_010 kohtaavat, eikä kumpikaan ole katettu liitoskohdassa. Sääntö on nyt
  yksi kysymys: **onko sillä seinällä johon pää osuu pintaa juuri
  liitoskohdassa.** Jos ei ole, venytys ei ansainnut paikkaansa. Tämä löysi
  scene_07000:sta katvepintaseinän joka oli **14.4 m liian pitkä** (30301 →
  15901 mm) — sen kaistasta poistui 392 GT-pistettä 201 037:stä, eli loppuosa oli
  aidosti tyhjää.
- **Kontrolli kaikilla viidellä Rohbau-scenellä: 21 m seinää leikattu, kattavuus
  ja tarkkuus ennallaan** (0.807–0.887 / 0.924–0.979). Viidellä desimaalilla
  suurin muutos oli scene_07000 kattavuus 0.87755 → 0.87746 eli 392 GT-pistettä
  4.3 miljoonasta. Leikkaus poisti vain sitä mitä siellä ei ollut.
- Asunnon `wall_005`:n 800 mm häntä jää tarkoituksella: sen vastinseinä
  `wall_ext_002` ON katettu liitoskohdassa, eli nurkka on aito.

## v0.9.19 (16.8.2026) — kattavuus 0.79 → 0.89, katvepintaan jäänyt seinä löytyy

Kaikki luvut mitattu Rohbau3D:n per-piste-GT:tä vastaan. Yleistyvyys viidellä
scenellä (vain 07000 on viritysaineisto): kattavuus 0.807–0.887, tarkkuus
0.924–0.979.

- **Välipohjan reuna ei ole enää seinä: tarkkuus 0.858 → 0.964 (scene_07002)
  ja 0.856 → 0.927 (scene_07003), kattavuus ennallaan.** Uusi `data/_rohbau_all.py`
  ajaa KAIKKI viisi Rohbau-sceneä — kynnykset on viritetty vain sceneen 07000,
  eikä yksi kohde kerro yleistyykö putki. Neljä ennen mittaamatonta sceneä
  paljastivat, että katvepintahaku teki kahdessa niistä valeseinän välipohjan
  reunasta (GT Beam 93 % ja 89 %). Ne olivat mittareilla **parempia kuin aidot
  seinät** (tuki 0.80–0.82 / jatkuvuus 0.89–0.97 vs aitojen 0.40–0.82), joten
  minkään kynnyksen nosto olisi poistanut väärät seinät.
  Erottava todiste on ALAREUNASSA: laatan reunan alla vaakataso jatkuu pinnan
  MOLEMMIN puolin, seinä katkaisee sen. Mitattu 7 ehdokkaasta neljällä
  scenellä: molemminpuolinen peitto **0.92** kummallakin palkkilinjalla,
  **0.00 kaikilla viidellä aidolla seinällä**. Ensimmäinen yritys ei purrut,
  koska hakuikkuna (±1,5 m emäseinän akselista) loppui juuri ennen testiä —
  1,5 m päässä olevalle ehdokkaalle jäi 15 mm käytettävää — joten ikkuna on
  nyt `_DECK_REACH` leveämpi kuin huippuhaku.
  Yleistyvyys viidellä scenellä: kattavuus 0.807–0.887, tarkkuus 0.924–0.979
  (paitsi 07003 0.927 ja 07001 0.940).
- **Toisen seinän takana ollut seinä löytyy nyt: Rohbaun kattavuus 0.792 →
  0.887, tarkkuus 0.918 → 0.924, 0 ongelmaseinää.** `cv2.findContours`
  jäljittää vapaan tilan reunan, eli se näkee vain ENSIMMÄISEN pinnan. Puolen
  metrin päässä betoniperimetristä seisova 30 m kipsiseinä ei ollut mallissa
  lainkaan — eikä yksikään detektorin kynnys olisi sitä löytänyt, koska pinta
  on maskin sisällä. Mittaus (`data/_gap_probe.py`, `data/_gap_view.py`):
  20,6 %:n vajeesta **52,6 % istui 400–700 mm päässä mallipinnasta**, ja
  Rohbau3D-GT:ssä ne pisteet ovat omia Drywall-instanssejaan (96–97 %).
  Uusi `core/semantics/second_face.py` etsii löydetyn seinän
  poikkileikkauksesta huiput mallipintojen ulkopuolelta. Ehdokas joutuu
  todistamaan neljä asiaa, jokainen omalla mittauksellaan:
  1. **Massa suhteessa emäseinän omaan pintaan** (≥ 10 %), ei absoluuttiseen
     pistemäärään — sama sääntö kuin muillakin laatumittareilla.
  2. **Väli on tyhjä.** Lattiasta kattoon ulottuvan hyllykön etupinta on
     geometrisesti sama kuvio kuin kipsiseinä — paitsi että hyllyssä ON
     HYLLYJÄ. Mitattu: synteettisen myymälän hyllyvälissä **6 vaakatasoa**
     (z = 500…5900, ~900 mm välein), Rohbaun kipsiseinän välissä **1**
     (palkkilinja z ≈ 5,1–5,5 m). Raja: ≥ 3 erillistä tasoa = hyllykkö.
  3. **Pinta on YKSI esine.** Sohva + kaappi + komero peräkkäin muodostavat
     yhtä pitkän "pinnan". Sarakkeittainen yläreuna erottaa ne: Rohbaun aito
     kipsiseinä IQR **4–9 mm** (0.00 × korkeus), asunnon huonekaluketju
     **1649 mm** (0.61 × korkeus).
  4. **Korkeus mitataan pinnasta, ei emäseinästä**, ja sen on oltava ≥ 20 %
     kerroskorkeudesta. Ilman tätä 10 m hallin vyötärömitta antaa 3 m
     kipsiseinälle hölynpölyluvut, ja 1,1 m korkea kanavalinja (tuki 0.96,
     jatkuvuus 0.96) menisi läpi seinänä — se pudotti tarkkuuden 0.884:ään.
  Vaihe ajetaan VASTA karsinnan jälkeen: aiemmat vaiheet (hyllynetupinta-
  poisto, dedup, napsautus) pitävät rinnakkaista seinäparia virheenä ja söivät
  ensimmäisessä yrityksessä molemmat (wall_012 ja wall_010 katosivat kokonaan).
  Muut aineistot ennallaan, ei uusia valeseiniä: myymälä 9, iso myymälä 9,
  asunto 13, kauppakeskus 12.
- **Laatumittarit eivät enää riipu keilaustiheydestä: karsinta kestää 1/5000
  harvennuksen ilman yhtään väärää poistoa (ennen murtui 1/250:llä).** Tuki,
  jatkuvuus ja karsinta nojasivat ABSOLUUTTISIIN pistemääriin (5 pistettä /
  500 mm sarake, 100 pistettä kaistassa, 50 vyötärölllä), jotka oli viritetty
  tiheillä keilauksilla. Harvalla skannilla aito seinä putosi kynnyksen alle ja
  karsiutui PALKKILINJANA — siis väärä POISTO, ei vain puuttuva lippu.
  `data/_density_probe.py` harventaa saman pilven ja ajaa mittarit uudelleen:
  | harvennus | pisteitä | ennen | jälkeen |
  |---|---|---|---|
  | 1/100 | 273,298 | 0 väärää | 0 |
  | 1/250 | 109,319 | **2 väärää poistoa** | 0 |
  | 1/1000 | 27,329 | 2 | 0 |
  | 1/5000 | 5,465 | 6 (koko malli) | **0** |
  Kolme korjausta, kukin omalla mittauksellaan:
  1. **Sarakkeen tuki on suhteellinen** (`_column_continuity`): sarake on
     tuettu jos siinä on ≥ 10 % sarakkeiden keskiarvosta. `data/_cont_rule_probe.py`
     mittasi erottelun aito−palkki eri tiheyksillä: kiinteä 5 pistettä romahti
     1/250:llä **0.94 → 0.00**, suhteellinen sääntö piti **0.79**. Palkkilinja
     erottuu yhä, koska sen pisteet kasautuvat pilarisarakkeisiin.
  2. **"Ei tarpeeksi arvioitavaksi" ≠ "palkkilinja".** Kolme porttia palautti
     jatkuvuuden `0.0` kun pisteitä oli alle 100 — se on karsintakäsky. Nyt ne
     erottavat "ei mitään" (haamu) ja "liian vähän" (`continuity = None`,
     ei karsita, näkyy tarkistuslistalla).
  3. **Lyhyttä seinää ei karsita jos paikalla on jotain.** Alle 4 m seinässä on
     liian vähän sarakkeita todistamaan mitään suuntaan. Erottelijaksi mitattiin
     pisteet ±1 m vyötäröllä, ja se on tyhjä vs ei-tyhjä — **ei tiheyskynnys**:
     Rohbaun perimetrihaamuilla 0 pistettä JOKA tiheydellä, aidoilla lyhyillä
     63 754 / 46 581 täydellä pilvellä ja yhä 36 / 27 kun pilvi on 1/2500.
  Rohbau ennallaan täydellä tiheydellä (0.792 / 0.918, 0 ongelmaseinää),
  myymälä 9, kauppakeskus 9, asunto 13.
- **Siirtynyt seinä napsautetaan nyt myös silloin kun sitä raapaisee jokin —
  ja siirto hyväksytään vasta jos MITATTU tuki paranee.** Ehto oli
  `support == 0`, joten aulan `wall_007` (8.8 m, oikea pinta 842 mm sivussa)
  jäi väliin: mallin pinnalla sattui olemaan hajapisteitä, tuki 0.17.
  Siirtyneisyys ei katoa siitä että seinää raapaisee jokin, joten portti on nyt
  `support < 0.50` (yli puoliksi keilattu pinta on jo oikeassa paikassa).
  **Mitattu aulassa: `wall_007` tuki 0.17 → 0.51, jatkuvuus 0.94 → 1.00**,
  mallin tuen mediaani 0.41 → 0.46.
  Pelkkä portin levennys kuitenkin REGRESSOI Rohbaun (kattavuus 0.792 → 0.749,
  tarkkuus 0.918 → 0.905), ja kontrolliajo `data/_ctrl_snapgate.py` osoitti
  kaksi eri juurisyytä — kumpikin korjattu:
  1. **Lyhyt seinä ei voi todistaa vastinettaan.** 500 mm sarakkeilla 1.0 m
     seinään mahtuu kaksi saraketta, joten jatkuvuusehto 0.80 täyttyy millä
     tahansa läiskällä: GT-aito `wall_ext_011` hyppäsi 400 mm ja sen oma tuki
     putosi 0.212 → 0.155. Alle 4 m seiniä ei siirretä (`_SNAP_MIN_COLS`).
  2. **"Lähin tiheä huippu" ei ole sama kuin "oikea paikka".** GT-aito 28 m
     `wall_008` (tuki 0.372) löysi huipun 138 mm sivusta ja siirtyi pois
     oikealta paikaltaan. Siirto hyväksytään nyt vain jos tuki paranee
     vähintään 0.10 — tuki mitataan samasta pilvestä molemmissa asennoissa,
     joten vertailu on suora eikä vaadi uutta kynnystä.
  Lopputulos: **Rohbau palautui bitilleen ennalleen** (0.792 / 0.918,
  identtiset akselit vanhan portin kanssa), aula paranee, ja myymälä (9),
  kauppakeskus (9) ja asunto (13) tuottavat saman seinämäärän kuin ennen.
- **Histogrammireititys mitattu vihdoin Matterport-aulalla — se ostaa
  kattavuutta 12× huonommalla vaihtokurssilla kuin contour.** Reitityksen
  trigger `_looks_like_retail` oli kirjattu "validoiduksi aulalla jota ei ole
  tässä repossa", eli sokea kohta. Aula on nyt paikallisesti, joten A/B ajettiin
  (`data/_lobby_ab.py`, `data/_lobby_cov.py`); aulassa ei ole GT:tä, joten
  tuomarina on pilvi itse — TUKI on tarkkuuden suunta, kaistan LUNASTETTU osuus
  kattavuuden suunta, ja nimittäjä on molemmille sama.
  | reititys | seiniä | seinäpituus | tuki med | lunastettu | tuki < 0.25 |
  |---|---|---|---|---|---|
  | auto = histogrammi | 17 | 120.9 m | 0.41 | 0.631 | 5 kpl / 24.2 m |
  | contour (auto pois) | 13 | 50.0 m | 0.60 | 0.564 | 2 kpl / 5.4 m |
  Histogrammi tuottaa 70.9 m lisää seinää ja saa siitä +6.7 pros.yks.
  lunastettuja pisteitä (0.09 pp/m); contourin oma kurssi on 1.13 pp/m.
  Sama kauppa kuin Rohbau-GT:llä (kattavuus +0.14 / tarkkuus −0.44), nyt
  itsenäisesti toisella aineistolla ja ilman GT:tä.
  **Reititystä EI käännetty**, koska histogrammi löytää aulan pitkät hyvin
  tuetut perimetriseinät jotka contour menettää (19.6 m tuki 0.64, 15.7 m 0.51,
  9.8 m 0.79, 9.3 m 0.92 — contourin pisin on 9.4 m). Korjattava on siis
  histogrammin heikko häntä, ei reititys. **Nykyinen karsinta ei yllä siihen:**
  heikot ovat *jatkuvia mutta tuettomia* (`wall_007` tuki 0.17 / jatkuvuus
  0.94), ja karsinta katsoo jatkuvuutta.
  **Korjaus samassa yhteydessä tehtyyn väitteeseen:** kirjasin ensin että
  kaikilla viidellä `support_offset` on `None` eli pintaa ei ole — se oli
  väärin. Kenttä lasketaan vain kun `support < 0.15 TAI continuity < 0.30`,
  eikä näillä kumpikaan täyttynyt, joten `None` tarkoitti "ei mitattu".
  Suoraan ajettuna kolme on aitoja haamuja, mutta **kaksi on siirtyneitä**
  (`wall_007` 842 mm, `wall_ext_013` 492 mm) — kynnyksen nosto olisi poistanut
  nekin.
  **Tuen kynnystä ei myöskään voi nostaa:** Rohbaun GT-aito `wall_ext_011` on
  tuki 0.21 (GT-puhtaus 0.90) eli aulan heikkojen 0.16–0.21 sisällä. Tuen taso
  seuraa keilausgeometriaa, ei seinän aitoutta (Rohbaun aidot 0.21–0.43, aulan
  0.17–0.92), joten globaali kynnys ei erottele. Oikea jatko on siirtyneiden
  napsautus, ei karsinnan kiristys.
- **Muisti mitattu uudelleen v0.9.18:lla: 38.3 min / 12.9 GB.** Luku 13.1 GB oli
  v0.9.0:sta, ja väliin mahtui ~80 committia (histogrammidetektori, hyllyfrontin
  poisto, pilarikorjaus, semanttisen suodattimen auto-valinta) — mikään niistä
  ei liikuttanut huippua. Sama halli (150×100 m, 32.0 M pistettä,
  `data/_scale_run.py data/_retail_l.ply`): **v0.9.0 42.5 min / 13.1 GB →
  v0.9.18 38.3 min / 12.9 GB**, huippu yhä `Semanttinen suodatin`issa, kaikki
  muut vaiheet ≤3.5 GB. **Uusi havainto:** suodattimen osuus AJASTA on noussut
  51 % → **77 %** (1767 s / 2298 s), koska detektiovaiheet ovat nopeutuneet
  eikä suodatin. Se on siis nyt sekä muistin ETTÄ ajan ainoa hallitseva vaihe.
  **Ei suoraa vertailua mallista:** v0.9.18 tuottaa samasta datasta 9 seinää /
  174 pilaria / 7 tilaa, kun v0.9.0 tuotti 37 / 97 / 2 — putki tekee eri työn,
  joten vertailukelpoinen on vain resurssiluku. Johtopäätös ennallaan: 12.9 GB
  ei jätä varaa 16 GB:n koneella, ja ainoa jäljellä oleva keino on suodattimen
  ajaminen XY-ruuduittain, mikä muuttaa tulosta ruutujen rajoilla.
- **Haamuseinät poistuvat nyt itsestään: Rohbaun ongelmaseinät 2 → 0.**
  `prune_unsupported_walls` säästi kaiken minkä `support_offset >= 250 mm`,
  koska iso etäisyys tulkittiin SIIRTYNEEKSI aidoksi seinäksi. Mitattu vika:
  `_nearest_surface` haki lähintä pintaa KOKO seinän korkeudelta, joten 10 m
  korkeassa kerroksessa histogrammin huippu osui lattian ja katon roinaan.
  Rohbaun `wall_ext_001` sai näin offsetin 442 mm ja `wall_ext_007` 825 mm,
  vaikka **kummallakaan ei ollut yhtään pistettä vyötärökorkeudella** — GT
  vahvistaa molemmat tyhjiksi (GT-puhtaus 0.00, luokka TYHJÄ). Haku siirretty
  samaan vyötärökaistaan (30–70 % korkeudesta) jolla jatkuvuus ja napsautus jo
  mittaavat, ja huipulta vaaditaan jatkuvuus — muuten metrin roinakasa 24 m
  seinän vieressä riittää suojaamaan haamun (yksikkötesti, offset oli 275 mm).
  Aito lyhyt seinä erottuu selvästi: `wall_ext_008` on vyötäröllä 63 754
  pistettä, haamuilla 0. Rohbau: **ongelmaseiniä 2 → 0**, kattavuus 0.792 ja
  tarkkuus 0.918 ennallaan (haamut olivat tyhjiä, eivät siis liikuttaneet
  pistepohjaisia lukuja — ne olivat malliin jääneitä valeobjekteja).
  **Ei vääriä poistoja:** kontrolliajo `data/_ctrl_waist.py` (vanha koko
  korkeuden haku patchattuna takaisin) antaa kolmella muulla aineistolla
  täsmälleen saman seinäjoukon — myymälä 9 → 9, kauppakeskus 9 → 9, asunto
  13 → 13. Kauppakeskuksen aito siirtynyt `wall_ext_010` säilyy, koska sen
  vastine on jatkuva pinta vyötäröllä (jatkuvuus 1.00).
- **Matterport-aula löytyi ja se sulki kaksi avointa validointiaukkoa.** Tiedosto
  ei ollut kadonnut vaan se on Matterportin JULKINEN näytetiedosto:
  `https://static.matterport.com/misc/UoqjwziqrZs-Aon_Lobby.e57` (1.15 GB,
  "Aon Lobby"). 9 asemaa, 58.3 M pistettä, 54 skybox-kuvaa — täsmää AGENTS.md:n
  merkintään "46 M pistettä, 9 asemaa" (46.6 M invalidien karsinnan jälkeen).
  Lähde on nyt kirjattu `AGENTS.md`:n testidatatauluun.
  1. **E57-lohkoluku sai ensimmäisen oikean testinsä.** 58.3 M > 40 M raja, eli
     ajo kulki uutta polkua: läpi **7.7 min, huippumuisti 6.8 GB**, 18 seinää,
     6 tilaa, 5 pilaria, 3 aukkoa. Aiemmin lohkoluku oli todennettu vain
     yhtäpitävyydellä 27.8 M tiedostolla, jossa se ei koskaan aktivoitunut.
  2. **Kuvaohjatun aukkodetektion refaktorointi on nyt todennettu oikealla
     datalla.** Vanha ja uusi `detect_image_openings` samoilla seinillä ja
     pilvellä: **täsmälleen samat 2 aukkoa** (ovi `wall_ext_000` 3360×2260 mm,
     ikkuna `wall_003` 2460×1460 mm), samat luvut kaikilta osin. Aika
     **23.21 s → 14.45 s**. Aiemmin tämä nojasi vain siihen että panoraaman
     korvaaminen mustalla kuvalla ei muuttanut tulosta synteettisellä datalla.
  **Rajoitus:** aulassa ei ole ground truthia, joten se todentaa yhtäpitävyyden
  ja sen että putki toimii — muttei ratkaise onko histogrammi- vai
  contour-detektori siellä parempi. Se vaatisi vision-tarkastelun tai GT:n.
- **Väärässä paikassa oleva seinä napsautetaan mitatulle pinnalle:
  kauppakeskuksen 99.8 m ulkoseinä 417 mm → 29 mm.** `support == 0` ei kerro
  onko kyse haamusta vai aidosta seinästä väärässä paikassa, ja ero ratkaisee
  toimenpiteen. Mitattu erottelija: löytyykö vyötärökorkeudelta ±1000 mm sisältä
  YHDENSUUNTAINEN ja JATKUVA vastine.
  | seinä | GT | vastine ±1000 mm | toimenpide |
  |---|---|---|---|
  | kauppakeskus `wall_ext_010` | aito, 417 mm sivussa | **388 mm, jatkuvuus 1.00** | siirretään |
  | Rohbau `wall_ext_001` / `_007` | tyhjä (0 GT-pistettä) | **ei vastinetta** | jää tarkistuslistalle |
  Tulos GT:tä vasten (`data/_retail_qa.py`): **GT01 lateraalivirhe 416.8 → 29.3 mm**,
  ja GT00/GT02/GT03 sekä löytyneet 9/9, hyllyvaleseinät ja ylimääräiset
  **bitilleen ennallaan**. Seinän pintatuki 0.000 → 1.0, eikä se ole enää
  tarkistuslistalla. Myymälä, asunto ja Rohbau: 0 siirrettyä.
  Tämä on eri asia kuin `_align_faces_to_surface_median`, joka hienosäätää jo
  ~oikeassa paikassa olevaa seinää 25 mm katolla; tässä seinä on satoja millejä
  pielessä eikä nykyinen sijainti ole säilyttämisen arvoinen. Siirto tehdään vain
  kun vastine on ≥80 % pituudelta, joten sirpale ei vedä seinää mukanaan.
  Kaksipuolinen seinä osaa asettua pintojen PUOLIVÄLIIN — ilman sitä mallin väärä
  pinta osuisi lähimmälle keilatulle pinnalle ja seinä jäisi kokonaisen paksuuden
  verran sivuun (mitattu synteettisellä: 187 mm jäännös). Viisi uutta testiä,
  174/174.
- **Palkkilinjalle tehty valeseinä POISTETAAN nyt automaattisesti — Rohbaun
  tarkkuus 0.510 → 0.918.** Pelkkä liputus vaati että käyttäjä klikkaa ne pois;
  nyt `prune_unsupported_walls` pudottaa ne ennen IFC:n kirjoitusta.
  Sääntö on kaksiosainen, ja **siirtymäraja on se joka tekee siitä turvallisen**:
  poistetaan vain kun jatkuvuus < 0.15 **JA** lähin pinta on alle 250 mm päässä.
  Mitattu ero on iso: palkkiseinien lähin pinta on 14–108 mm (= palkin oma
  pinta), kun taas AITO seinä väärässä paikassa löytää vastineensa 375–825 mm
  päästä. Siksi kauppakeskuksen `wall_ext_010` — aito GT-seinä 375 mm sivussa —
  jää malliin ja tarkistuslistalle sen sijaan että katoaisi.
  | data | seiniä | poistettu | tulos |
  |---|---|---|---|
  | Rohbau site_07 | 14 | **6** | kattavuus 0.796 → **0.792**, tarkkuus 0.510 → **0.918**, ongelmaseiniä 8 → 2 |
  | myymälä 72×48 m | 9 | **0** | 9/9 GT-seinää, 0 hyllyvaleseinää, pilarit 34/34 (ennallaan) |
  | kauppakeskus 150×100 m | 37 | **0** | ennallaan, aito siirtynyt seinä säilyy |
  | asunto | 15 | **0** | ennallaan |
  Aukot siivotaan poistetun seinän mukana, muuten IFC:hen jäisi aukkoja joiden
  seinää ei ole (GUI:n oma poisto ei tätä tee). Neljä uutta testiä. 169/169.
- **Palkkilinjalle tehty valeseinä jää nyt kiinni: Rohbau 2/8 → 8/8, nolla
  väärää hälytystä.** Edellinen pintatukisääntö näki vain PUUTTUVAN pinnan, ja
  histogrammidetektorin 28 m valeseinillä pintaa ON — ne istuvat palkiston
  päällä, jossa on lattia, katto, palkki ja pilarit, eli pisteitä joka
  korkeudella. Ratkaiseva ero on **pituussuuntainen jatkuvuus vyötäröllä**
  (30–70 % korkeudesta, 500 mm sarakkeet): aito seinä on yhtenäinen, palkkilinja
  on pilareita 8 m välein. Mitattu Rohbau-GT:llä: **aidot 0.50–1.00, palkkiseinät
  0.05–0.07** → kynnys 0.30 istuu 7-kertaiseen väliin.
  | data | vanha `conf` | pelkkä pintatuki | **tuki + jatkuvuus** |
  |---|---|---|---|
  | Rohbau site_07 (8 huonoa / 14) | 1/8 | 2/8 | **8/8, 0 väärää** |
  | myymälä 72×48 m (24 seinää) | 0 | 0 | **0** |
  | kauppakeskus 150×100 m (37) | 0 | 1 (oikea) | **1 (oikea)** |
  | asunto (15) | 1 **väärä** | 0 | **0** |
  **Hypoteesi jonka mittaus kumosi — älä toista:** oletin että palkkiseinällä on
  tukea vain katon alla. Päinvastoin: pystytuen osuus on palkkiseinillä
  **0.92–1.00** ja aidoilla **0.63–0.94**, eli pystyprofiili erottelee väärään
  suuntaan. Vain vyötärön jatkuvuus toimii (`data/_vprofile_probe.py`).
  **Liputus, EI hylkäys.** Kauppakeskuksen `wall_ext_010` on GT[1] eli aito
  100 m ulkoseinä 417 mm sivussa — sen poistaminen hävittäisi oikean seinän.
  Siksi sama sääntö erottaa yhä kaksi tapausta (`_nearest_surface`): "pinta
  375 mm sivussa — siirrä tai poista" vs. "ei yhtenäinen seinä (5 % vyötäröstä)
  — mahdollinen palkki- tai pilarilinja". Kolme uutta testiä; palkkilinjatesti
  kaatuu jos jatkuvuussääntö ablatoidaan pois, ja se tarkistaa erikseen että
  pintatuki on yli kynnyksen (muuten testi ei erottelisi mitään). 165/165.
  **Mitä liputus on arvoltaan, mitattuna:** kun 8 liputettua seinää poistetaan
  Rohbau-mallista, kattavuus laskee 0.796 → **0.792** (−0.004) ja tarkkuus
  nousee 0.510 → **0.918**, ongelmaseiniä 8 → **0**. Ne kahdeksan eivät siis
  tuoneet kattavuutta käytännössä lainkaan, mutta puolittivat tarkkuuden.
  | | kattavuus | tarkkuus |
  |---|---|---|
  | contour (aiempi kirjattu paras) | 0.653 | 0.951 |
  | histogrammi (nykytuotanto) | **0.796** | 0.510 |
  | histogrammi + liputetut poistettu | **0.792** | **0.918** |
  Yhdistelmä siis voittaa molemmat: kattavuus +0.139 contouriin nähden ja
  tarkkuus vain −0.033 sen alle. **Malli itsessään ei silti parane** — tämä
  vaatii että käyttäjä poistaa ne Tarkistus-välilehdellä. Automaattinen hylkäys
  maksaisi mitatusti vain 0.004 kattavuutta, mutta se on erikseen päätettävä:
  kauppakeskuksen `wall_ext_010` on aito GT-seinä 417 mm sivussa, eikä sitä saa
  poistaa automaattisesti.
- **MITTAUS (ei muutos): iso+korkea kohde reitittyy histogrammille ja tarkkuus
  puolittuu paljaalla rungolla.** Rohbau site_07/scene_07000 on ainoa data jossa
  on per-piste-GT, ja siihen ajettuna nykytuotanto tulostaa diagnostiikkaan
  "liiketila → histogrammi-detektori": `_looks_like_retail` on käytännössä
  "pohja-ala + korkeus ≥4.5 m", jonka ~10 m betonirunko täyttää. Kontrolliajo
  samalla koodilla auto-reititys patchattuna pois (`data/_ctrl_contour.py`):
  | detektori | kattavuus | tarkkuus | ongelmaseiniä |
  |---|---|---|---|
  | histogrammi (auto, tuotanto) | **0.796** | **0.510** | 8 / 14 |
  | contour (auto pois) | 0.653 | **0.951** | 4 / 18 |
  Contour toistaa aiemmin kirjatut 0.96 ja 0.65 → mittari ei ole rikki, ero on
  aito. Kuusi 28 m valeseinää istuu PALKEILLA (GT Beam 93–96 %). Kauppa on
  kattavuus +0.14 vs. tarkkuus −0.44.
  **Ei korjattu tässä**, koska trigger on validoitu Matterport-aulalla jota ei
  ole tässä repossa eikä tällä koneella — sen rikkominen ei näkyisi missään
  paikallisessa testissä. Ks. AGENTS.md "Tunnetut rajoitukset".
- **Kuvaohjattu aukkodetektio: testit + 15.9 s → 0.08 s, kun kuvien dekoodaus
  osoittautui käyttämättömäksi.** `image_openings.py` oli ainoa detektori ilman
  yhtään testiä, vaikka se kirjoittaa asiakkaan IFC:hen ikkunoita ja aktivoituu
  juuri isoilla E57-keilauksilla. Seitsemän testiä synteettisellä seinällä ja
  asemalla: läpinäkyvä aukko löytyy ikkunana, lattiaan asti ulottuva ovena,
  maalattu umpiseinä ei tuota mitään, kaluste edessä (okkluusio >60 %) ohittaa
  seinän, vino asema (cosang <0.6) ei kelpaa, lyhyt seinä ohitetaan, ja
  kuvaton E57 on no-op. Testeissä on hampaat: syvyyspuskurin ablaatio pudottaa
  löydöt nollaan.
  Testejä kirjoittaessa paljastui että **panoraama ei vaikuta tulokseen
  lainkaan**. `equi` laskettiin (`H, W = equi.shape[:2]`) mutta `H`/`W` eivät
  esiinny sen jälkeen missään — päätös tulee kokonaan pistepilven
  syvyyspuskurista. Todennettu korvaamalla panoraama mustalla 4×8-kuvalla:
  sama aukko, samat mitat (`2280 / 1440 / 980 / 1040 mm`). Kuvia siis
  tarvitaan vain asemien SIJAINTIIN ja piirteen porttina, ei pikseleinä, joten
  `_load_stations` lukee enää poset eikä pura JPEGejä, ja `_equirect` +
  `_quat_to_R` poistuivat. **Mitattu `parking-lot-updated.e57` (285 kuvaa):
  asemat identtiset (1 → 1, sama translaatio 4 desimaalin tarkkuudella),
  aika 15.90 s → 0.08 s.**
- **Poistettu kuollut koodi `gui/pano_view.py` + `gui/photo_view.py`.**
  Panoraamavälilehti poistettiin jo commitissa `6bc8cd5` ("keep viewer modules
  as detection libs"), mutta mikään ei importannut niitä: `image_openings.py`
  tekee oman käsittelynsä. ~600 riviä joka meni exeen mukana turhaan.
- **Iso E57 luetaan lohkoissa — ennen 32 GB tiedosto ei olisi latautunut
  lainkaan.** `loader._load_e57` luki jokaisen skannin `read_scan`illa ja
  yhdisti ne kokonaisuudessaan muistiin ennen kuin z-kaistaa oli edes rajattu,
  ja `streaming.load_floor_slice`:n lohkoluku koski vain `.ply`:tä. Mitattu
  `gargage.e57`:llä: 0.56 GB → 27.8 M pistettä, huippu-RSS **2.79 GB** eli
  ≈5 GB per tiedosto-GB → **32 GB e57 ≈ 1.6 mrd pistettä ≈ 159 GB RSS.**
  Per-skanni-rajaus ei olisi auttanut: iso keilaus on **yksi** skanni
  (gargage 27.8 M / 1 skanni). Sama libE57-lukija palvelee lohkoittain, joten
  `_e57_scan_chunks` täyttää kiinteän puskurin toistuvasti
  (`libe57.CompressedVectorReader`), soveltaa posen ja pudottaa invalidit;
  `e57_band_chunks` suodattaa z-kaistan, `read_e57_xyz_band` täyttää
  esivaratun taulukon kahdella passilla (kuten PLY), `read_e57_z` ja
  `e57_z_range` hoitavat kerrostunnistuksen ja kaistarajat lataamatta
  tiedostoa — molemmat latasivat ennen koko pilven pelkän Z:n takia.
  **Yhtäpitävyys todennettu, ei päätelty:** kaistan pistejoukko on identtinen
  koko lukuun nähden (449 240 = 449 240, järjestetyt taulukot samat), ja
  huippumuisti 2.79 → **0.60 GB**.
  **Portitettu ≥40 M pisteeseen, sama sääntö kuin PLY:llä, koska lohkoluku ei
  ole tulokseltaan neutraali:** voxelointi tapahtuu lohkorajoilla ja
  kerroshistogrammi luetaan desimoituna → kerrosraja siirtyy senttejä. A/B
  samalla koodilla gargage.e57:llä: kaista −2.21…2.60 m → −2.21…**2.57** m ja
  malli 11 seinää / 2 tilaa / 14 pilaria → **9 / 1 / 15**. Tiedostot jotka
  latautuvat jo nyt pitävät siis validoidun polkunsa (gargage 27.8 M < 40 M).
  Seitsemän testiä; pose-testi kaatuu jos posen sovellus ablatoidaan pois.
- **Tarkistus-lista mittaa nyt pilveä, ei kysy detektorilta.** Vika oli
  mittarissa, ei kynnyksessä: `confidence` on kokoproxy (`wall_contour`:
  `0.80 + pituus/20000`, `wall_density`: `pituus/5000`, aukoilla
  `leveys × korkeus`), joten **mitä pidempi elementti, sitä varmempi** — ja
  pahimmat valeseinät ovat pitkiä. Seuraus oli mitattavissa: 65 mallin otoksessa
  kauppakeskus (37 seinää + 174 pilaria) ja myymälä (24 + 34) liputtivat
  molemmat **0 elementtiä**, vaikka virheet tiedettiin.
  Tilalle `Wall.support`: kuinka suuri osa seinän pinnasta on oikeasti keilattu
  (200 mm ruudukko pinnan ±80 mm kaistassa). Kun tuki alittaa 0.15,
  `_nearest_surface` erottaa vielä kaksi tapausta, koska toimenpide on eri:
  "pinta 442 mm sivussa — siirrä tai poista" vs. "ei pintaa pilvessä".
  **Mitattu nykykoodilla (v0.9.18) Rohbau3D:n per-piste-GT:tä vasten**,
  site_07/scene_07000, 14 seinää joista GT:n mukaan 8 virheellistä:
  | sääntö | liputti | oikein | vääriä |
  |---|---|---|---|
  | vanha `conf < 0.40` | 1 | 1/8 | 0 |
  | uusi `tuki < 0.15` | 2 | **2/8** | **0** |
  Parannus on siis aito mutta pieni, ja **raja tulee vastaan mitattavasti**:
  kuusi 28 m valeseinää istuu PALKKIEN päällä (GT-puhtaus 0.03–0.11) ja palkki
  on aito keilattu pinta, joten niiden peitto on 0.179–0.248 — päällekkäin
  aitojen seinien (0.212–0.427) kanssa. **Mikään peittokynnys ei erota niitä.**
  Sama juurisyy kuin hyllyfrontissa: pinta on oikea, paikka on väärä.
  Historiallinen huomio: v0.9.0:n Rohbau-mallilla sama sääntö nappasi 6/6,
  koska silloin virheet olivat aidosti tyhjiä seiniä. **Kynnys on validoitava
  uudelleen aina kun detektori muuttuu** — virhepopulaatio vaihtuu sen mukana.
  Vanhalla v0.9.0-pohjalla mitattiin lisäksi: asunnon v0.8.8-haamuseinä
  liputtui oikein (vanha sääntö missasi sen kokonaan), v0.9.0-asunnon **väärä**
  hälytys (`wall_ext_002`, tuki 0.31) poistui, ja kauppakeskuksesta löytyi
  `wall_ext_010` — 99.8 m perimetriseinä jonka nimellisillä pinnoilla on 0
  pistettä mutta ±600 mm:n sisällä 593 152, eli ~375 mm sivussa. Nämä ovat
  ajamatta nykykoodilla.
  **Varmennettu visionilla** (`data/_wall_view.py`): vyötäröleikkauksessa on
  yhtenäinen pinta −525 mm akselista koko 99.8 m matkalta, mallin pinnat
  (±150 mm) ovat tyhjässä ilmassa, ja ne 2907 "pinnalla" olevaa pistettä ovat
  lattiaa ja kattoa (z≈0 ja z≈8.5 m). Ei siis haamu vaan aito seinä väärässä
  paikassa — eron näkee vain kuvasta, `support` on kummassakin tapauksessa 0.
  Vertailuksi `wall_000`: mallin pinnat istuvat tiheällä pisteviivalla,
  31 481 pistettä koko korkeudelta ja koko pituudelta.
  Hinta mitattu: **6.2 s / 32 M pistettä / 37 seinää**, sama XYIndex-kaistahaku
  jota QA jo käyttää. Viisi uutta testiä; haamuseinätestit kaatuvat jos
  pintatukisääntö ablatoidaan pois. 148/148 testiä läpi.
  **Ei korvaa `remove_shelf_front_walls`-sääntöä** eikä yritä: pintakohtaiset
  mittarit eivät erota hyllyn etupintaa seinästä (hylly tuki 0.972, aidot
  0.924–1.0; sama kohinalla ja pinnan takaisella tilalla). Erottelu vaatii
  kontekstin tai semantiikan.

## v0.9.18 (10.8.2026) — laatukorjaukset (IFC-tekijyys, CLI-detektori, loader-varoitukset)

- **IFC ei enää nimeä kehittäjää tekijäksi.** Writer kovakoodasi jokaisen
  tuotetun IFC:n `IfcPerson`-tekijäksi kehittäjän nimen (Rekola/Lauri) ja
  sovellusversioksi vanhentuneen `0.1.0`:n → asiakkaan IFC:ssä olisi lukenut
  väärä henkilö. Nyt tekijyys on neutraali (`IfcPerson.Identification="scan2bim"`,
  ei henkilön nimeä) ja versio = todellinen sovellusversio.
- **CLI-detektorin oletus korjattu: `ransac` → `contour`.** `scan2bim convert`
  pakotti `--detector`-oletukseksi `ransac`in (hidas, epädeterministinen fallback)
  vaikka tuotannon oletus on `contour`; komentorivikäyttäjä sai siis huonomman
  detektorin eikä voinut edes valita oikeita (`contour`/`histogram`). Nyt oletus =
  `contour` (sama kuin PipelineConfig ja GUI) ja valinnat kattavat todelliset
  detektorit. Testi vartioi ettei oletus enää eroa tuotannosta.
- **Vajaan/vaurioituneen syötetiedoston selkovaroitus laajennettu E57/LAS/PTS/XYZ:lle.**
  Aiemmin vain binääri-PLY tunnisti katkenneen siirron (headerin lupaama pistemäärä
  vs. tavuista laskettu todellinen). Nyt myös E57 (lukukelvottomat skannit),
  LAS/LAZ (header point_count vs. luettu) ja PTS/XYZ (lukukelvottomien rivien osuus)
  varoittavat selkokielellä tai nostavat selkovirheen tyhjästä/vakavasti vajaasta
  tiedostosta — ei enää äänetöntä osittaista mallia tai kryptistä kaatoa. 143 testiä.

## v0.9.12 (5.8.2026) — itsepäivityksen varmennus

- Sama korjattu apuprosessi-itsepäivitys kuin v0.9.11; julkaistu jotta korjatun
  version sisäinen päivitys voidaan varmistaa toimivaksi päästä päähän. Ei muita
  muutoksia.

## v0.9.11 (5.8.2026) — itsepäivitys viimeinkin toimii (one-dir vaihto apuprosessilla)

- **Itsepäivitys asentaa nyt one-dir-version oikein.** Edellinen korjaus (v0.9.9)
  purki zipin, mutta vaihto kaatui käynnissä olevan sovelluksen lukitsemaan
  `base_library.zip`-tiedostoon (Windows-virhe 32). Nyt vaihdon tekee pieni
  apuprosessi, joka odottaa sovelluksen sulkeutumista, kopioi uuden version
  paikalleen ja käynnistää sovelluksen automaattisesti uudelleen. Todennettu
  hiekkalaatikossa (lukittu tiedosto → apuri odotti → vaihtoi oikein). 134 testiä.

## v0.9.10 (5.8.2026) — itsepäivityksen varmennus

- Sama korjattu itsepäivitys kuin v0.9.9; julkaistu jotta korjatun version (0.9.9)
  sisäinen päivitys voidaan varmistaa toimivaksi päästä päähän. Ei muita muutoksia.

## v0.9.9 (5.8.2026) — KRIITTINEN: itsepäivitys ei enää riko sovellusta

- **Itsepäivitys korjattu.** Sovelluksen sisäinen "päivitä"-toiminto rikkoi
  asennuksen ("Sovellus ei toimi tietokoneessasi") — se kirjoitti päivityspaketin
  (zip) sellaisenaan `scan2bim.exe`:ksi purkamisen sijaan, jolloin ohjelma ei ollut
  enää ajettava. Nyt zip puretaan ja vaihdetaan tiedosto kerrallaan oikein.
  **Kaikissa aiemmissa versioissa (0.9.1–0.9.8) tämä oli rikki**, joten korjattuun
  versioon on päästävä KERRAN asennusohjelmalla (Setup.exe); sen jälkeen sisäinen
  päivitys toimii. 133 testiä läpi.

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

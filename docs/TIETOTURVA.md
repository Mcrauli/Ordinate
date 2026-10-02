# Ordinate — tietoturvaseloste

Tämä kuvaa mitä Ordinate tekee koneella ja verkossa. Sama teksti on asennuskansiossa (`TIETOTURVA.md`) ja nettisivulla. Kaikki väitteet on
tarkistettu lähdekoodista versiossa 0.9.37.

## Lyhyesti

- Ordinate on tavallinen Windows-työpöytäohjelma. Se ajetaan **käyttäjän
  omilla oikeuksilla**, eikä se pyydä ylläpitäjän oikeuksia käytön aikana.
- Pistepilviä, malleja tai muita käyttäjän tiedostoja **ei lähetetä mihinkään**.
  Kaikki laskenta tehdään omalla koneella.
- Ohjelmassa ei ole käyttäjätiliä, lisenssipalvelinta eikä telemetriaa.
- Ainoa verkkoyhteys on päivitysten tarkistus GitHubista, ja sen voi kytkeä
  pois ryhmäkäytännöllä. Silloin ohjelma ei ota verkkoon yhteyttä lainkaan.
- Päivitykset ovat **julkaisijan allekirjoittamia**. Ohjelma hylkää päivityksen,
  jonka allekirjoitus ei täsmää.

## Asennus

- Asennusohjelma asentaa oletuksena **vain nykyiselle käyttäjälle**
  (`%LOCALAPPDATA%\Programs\Ordinate`) ilman ylläpitäjän oikeuksia. Koko koneelle
  asentaminen on mahdollista erikseen ylläpitäjänä.
- Asennus luo pikakuvakkeet ja Windowsin tavalliset poistomerkinnät
  (Asetukset → Sovellukset). Muita rekisterimuutoksia ei tehdä.

## Mitä ohjelma lukee ja kirjoittaa

| Mitä | Missä |
|---|---|
| Pistepilvet, jotka käyttäjä itse avaa | lukee vain valitut tiedostot |
| Tulokset (IFC, DXF, JSON, korjaukset) | käyttäjän valitsema tulostekansio |
| Ajohistoria (kesto, määrät, koneen tiedot) | `%APPDATA%\Ordinate` |
| Väliaikaistiedostot ja loki | `%TEMP%` |
| Päivityskäytäntö (vain luku) | `HKLM`/`HKCU\SOFTWARE\Policies\Ordinate` |

Ohjelma ei lue muita kansioita, selaimen tietoja, salasanoja eikä muiden
ohjelmien tietoja. Windows-istunnon oikeudet ovat samat kuin millä tahansa
käyttäjän käynnistämällä ohjelmalla. Halutessaan IT voi ajaa Ordinatea
erillisellä rajatulla käyttäjätilillä.

## Verkkoyhteydet

| Yhteys | Milloin | Mitä lähtee |
|---|---|---|
| `api.github.com` | käynnistyksessä, ellei kytketty pois | pyyntö julkaisulistasta, ei käyttäjätietoja |
| `github.com` ja GitHubin latauspalvelin | vain kun käyttäjä painaa "Päivitä nyt" | ei mitään, vain lataus |

Ohjelmassa ei ole muita verkkoyhteyksiä.

## Päivitykset

- Päivitys **ei asennu itsestään**. Ohjelma näyttää ilmoituksen, ja käyttäjä
  päättää painaako "Päivitä nyt".
- Jokaisen päivityspaketin rinnalla julkaistaan `<paketti>.sig.json`, jossa on
  paketin nimi, versio, SHA-256-tarkiste ja koko **Ed25519-allekirjoitettuna**.
  Yksityinen avain on vain julkaisijalla, julkinen avain on ohjelman sisällä.
- Ennen asennusta ohjelma tarkistaa allekirjoituksen, että se koskee juuri
  tätä tiedostoa ja versiota, ja että ladatun tiedoston tarkiste ja koko
  täsmäävät. Jos jokin ei täsmää, päivitystä ei asenneta. Näin paketin
  vaihtaminen latauspalvelimella ei riitä väärennetyn version levittämiseen.

### Päivitysten kytkeminen pois

Koko koneelle (ylläpitäjä, voidaan jakaa ryhmäkäytännöllä):

```
reg add "HKLM\SOFTWARE\Policies\Ordinate" /v DisableUpdateCheck /t REG_DWORD /d 1 /f
```

Yhdelle käyttäjälle: sama `HKCU`:hun, tai ympäristömuuttuja
`ORDINATE_DISABLE_UPDATES=1`. Ohjelman lokiin tulee tällöin
"Päivitystarkistus pois päältä". Päivitykset asennetaan silloin käsin
asennusohjelmalla.

## Latauksen aitouden tarkistus

Jokaisen julkaisun tiedostojen rinnalla on `.sha256` ja `.sig.json`.
Asennetulla Ordinatella voi tarkistaa minkä tahansa ladatun tiedoston:

```
"%LOCALAPPDATA%\Programs\Ordinate\ordinate-cli.exe" verify Ordinate-Setup-0.9.37.exe
```

Komento tulostaa `AITO` vain, jos allekirjoitus on julkaisijan ja tiedosto
on muuttumaton.

## Diagnostiikka

"Lähetä diagnostiikka kehittäjälle" **ei lähetä mitään itse**. Se tallentaa
tekstitiedoston työpöydälle ja avaa sähköpostiluonnoksen. Käyttäjä voi lukea
tiedoston ennen kuin liittää sen. Tiedostossa on ajojen kestot,
tunnistettujen elementtien määrät, syötetiedostojen nimet ja koot sekä
koneen käyttöjärjestelmä, suoritin ja muisti. Siinä **ei ole** pistepilviä,
geometriaa eikä mallin sisältöä.

## Tiedossa olevat rajoitukset

- Ohjelmatiedostoja **ei vielä ole allekirjoitettu Authenticode-varmenteella**,
  joten Windows SmartScreen voi varoittaa tuntemattomasta julkaisijasta.
  Koodinallekirjoitusvarmenne on hankinnassa. Siihen asti aitouden voi
  tarkistaa yllä olevalla `verify`-komennolla tai SHA-256-tarkisteesta.
- Lähdekoodi ei ole julkinen. Käytetyt avoimen lähdekoodin komponentit ja
  niiden lisenssit on lueteltu tiedostossa `THIRD-PARTY-NOTICES.md`, joka
  toimitetaan ohjelman mukana.

## Haavoittuvuuksien ilmoittaminen

Sähköposti: rekolalauri@gmail.com. Ilmoitukseen vastataan ja korjauksen
aikataulu kerrotaan.

# Rename-migraatiosuunnitelma: scan2bim → Ordinate

Status: **VALMIS ODOTTAMAAN** — ei aloiteta ennen kuin lukitusportti (alla) on vihreä.
Laadittu 5.8.2026. Liittyy nimibriefiin `docs/superpowers/specs/2026-07-15-nimibrief-design.md`.

---

## 0. Lukitusportti (EI koodia ennen tätä) — käyttäjän toimet

Rename ei ala ennen kuin **molemmat** ovat lukossa:

1. **Domainit rekisteröity:** `ordinate.io` + `ordinate.fi` (olivat vapaita 15.7.2026;
   tarkista uudelleen ennen ostoa). Halpaa → tee heti, estää squattauksen.
2. **Tavaramerkki haettu:** EUIPO + PRH, luokat **9** (ohjelmisto) ja **42** (SaaS/
   suunnittelupalvelu). Törmäystarkistus oli puhdas AEC/BIM-vertikaalissa (websearch
   15.7.), mutta muodollinen haku on ainoa varmistus. Jos konflikti → nimi vaihtuu →
   ilman lukitusta tekisimme renamen kahdesti.

Kunnes portti on vihreä, pilotti (Radikal) pyörii sisäisesti nimellä "scan2bim".

---

## 1. Strategian ydin: erota NÄKYVÄ brändi ja NÄKYMÄTÖN putkitus

**Nimetään uudelleen VAIN se minkä käyttäjä näkee. Pidetään sisäinen putkitus
ennallaan** — kolmesta syystä se on sekä turvallisin että pienin muutos:

### 1a. PIDÄ ennallaan (näkymätön, self-update-landmine tai pelkkää churnia)

| Kohde | Miksi EI nimetä | Todiste |
|---|---|---|
| **exe-tiedostonimi `scan2bim.exe`** | Jo asennettujen versioiden `updater.extract_zip` **hardkoodaa** etsivänsä `scan2bim.exe` zipistä (updater.py:361). Jos uusi zip sisältää `ordinate.exe`, VANHAT asennukset eivät löydä sovellushakemistoa → **self-update rikkoutuu**. Lisäksi `replace_app_dir` ei poista vanhoja tiedostoja → orpo `scan2bim.exe` jää + pikakuvake osoittaa siihen → jää päivityksettä. | updater.py:361, :334–348 |
| **release-repo `Mcrauli/scan2bim-web`** | `updater.DEFAULT_REPO` on hardkoodattu (updater.py:34). Kaikki asennetut versiot pollaavat sitä. Repon uudelleennimeäminen luottaisi GitHubin 301-redirectiin API:ssa (hauras). Distribuutiorepon nimi ei ole brändi- eikä juridiikka-asia. | updater.py:34 |
| **Python-paketti `scan2bim`** (import-nimi) | Näkymätön käyttäjälle. Uudelleennimeäminen `ordinate`:ksi koskee **71 tiedostoa** + pyproject + spec + console-skriptit → iso churn, ei käyttäjähyötyä, konfliktiriski aktiivisen kehityksen kanssa. | `grep -rl scan2bim src/ tests/` = 71 |

→ **"scan2bim" jää eloon vain sisäisenä artefaktinimenä ja jakelurepona — kumpikaan ei
ole se mitä asiakas näkee tai mistä juridiikka välittää.** Assettien `.zip`/`Setup.exe`
saa nimetä vapaasti (updater tunnistaa ne päätteestä/"setup"-sanasta, EI "scan2bim"-
nimestä, updater.py:82–93) — mutta ZIPIN SISÄLLÄ oleva exe pysyy `scan2bim.exe`.

### 1b. NIMETÄÄN Ordinate:ksi (kaikki mitä käyttäjä näkee)

Katso täydellinen inventaario §2.

### 1c. Myöhempi vaihe (valinnainen, iso versio esim. 2.0)

Kun vanha asennuskanta on migratoitunut (kaikki self-updannut uuteen), voi tehdä
"puhtaan" renamen: paketti + exe + repot + siirtymä-updater joka (a) sietää
`ordinate.exe`:n `extract_zip`:ssä, (b) siivoaa vanhan exen, (c) kirjoittaa pikakuvakkeet
uusiksi. EI tehdä v1.0:ssa — landmine ei ole vaivan arvoinen ennen myyntiä.

---

## 2. Inventaario: näkyvät kohdat (nimetään Ordinate)

### Sovellus (GUI)
- `src/scan2bim/gui/main_window.py:25` — `setWindowTitle(f"scan2bim  v{__version__}")` → `Ordinate`
- `src/scan2bim/gui/main_window.py:48` — `QLabel("scan2bim")` (otsikkopalkin brändi) → `Ordinate`
- `src/scan2bim/gui/brand.py` — piirtää "scan2bim"-logomerkin QPainterilla → uusi Ordinate-merkki
- `src/scan2bim/gui/feedback.py:47` — dialogin otsikko `f"scan2bim diagnostiikka & palaute"` → `Ordinate`
- **Keskitä brändinimi yhteen vakioon** (esim. `src/scan2bim/_brand.py: APP_NAME = "Ordinate"`)
  ja viittaa siihen kaikkialta → jatkossa yhden rivin muutos.

### Ikoni / assetit
- `assets/scan2bim.ico` → uusi `assets/ordinate.ico` (uusi kuvitus). Spec viittaa siihen:
  `build/scan2bim.spec:57` `_icon_path = ...'scan2bim.ico'`.
- `assets/scan2bim.svg` (jos on) → Ordinate-logo.

### Installer (Inno Setup) — `build/installer.iss`
- `AppName=scan2bim` → `Ordinate` (rivi 26)
- `AppVerName=scan2bim {#AppVersion}` → `Ordinate {#AppVersion}` (rivi 28)
- `DefaultDirName={autopf}\scan2bim` → `{autopf}\Ordinate` (rivi 33) ⚠ ks. §3 (uusi
  asennushakemisto vain UUSILLE asennuksille; vanhat pysyvät vanhassa polussa)
- `DefaultGroupName=scan2bim` → `Ordinate` (rivi 34)
- `AppPublisherURL/SupportURL/UpdatesURL` (rivit 30–32) → osoittavat `Mcrauli/scan2bim`-
  repoon; päivitä jos dev-repo nimetään (ks. §1c), muuten jätä.
- Pikakuvakkeen nimi ("scan2bim" → "Ordinate"), mutta **kohde pysyy `scan2bim.exe`**.
- `OutputBaseFilename` / asennustiedoston nimi → `Ordinate-Setup` (saa vaihtaa).

### version_info (näkyy exen ominaisuuksissa) — `build/version_info.py`
- `CompanyName`, `FileDescription`, `ProductName`, `InternalName`, `OriginalFilename`,
  `LegalCopyright` → Ordinate. HUOM `OriginalFilename` saa lukea `ordinate.exe` (metatieto),
  mutta itse tiedosto pysyy `scan2bim.exe` (§1a) — TAI pidä metatietokin scan2bim.exe
  ristiriidan välttämiseksi. Suositus: metatiedot Ordinate, `OriginalFilename` = tosi
  tiedostonimi `scan2bim.exe`.

### Dokumentit ja markkinointi
- `README.md` (loppukäyttäjän kuvaus) → Ordinate + uusi tagline/logo
- Website-repo `Mcrauli/scan2bim-web` → `index.html` (12 "scan2bim"-esiintymää, 0
  "ordinate"), `README.md`, logo, favicon, otsikko, download-copy. **Sivun sisältö =
  Ordinate; repon NIMI pysyy scan2bim-web (§1a).**
- `CHANGELOG.md` — lisää `## vX.Y.0 — tuotenimi Ordinate` -merkintä; vanhoja rivejä EI
  muuteta (historia).
- Sisäiset kehittäjädokumentit (`AGENTS.md`, `CLAUDE.md`, `docs/*`, `THIRD-PARTY-NOTICES.md`):
  näissä "scan2bim" viittaa PAKETTIIN/putkitukseen joka pysyy → **jätä ennalleen**,
  lisää vain huomautus "tuotenimi = Ordinate, paketti/exe = scan2bim (sisäinen)".

---

## 3. Erikoishuomiot self-updaten ja asennuspolun kanssa

1. **exe pysyy `scan2bim.exe`** (§1a). Kaikki näkyvä on Ordinate; vain Program Filesissä
   binäärin nimi on scan2bim.exe. Hyväksyttävä kompromissi v1.0:ssa.
2. **release-repo pysyy `scan2bim-web`.** Uudet assetit voivat olla `Ordinate-*.zip` /
   `Ordinate-Setup.exe` — updater tunnistaa ne päätteestä. Kiinteänimi `scan2bim-Setup.exe`
   jonka SIVU linkittää: joko pidä nimi tai päivitä sivun linkki uuteen kiinteänimeen
   SAMASSA julkaisussa.
3. **`DefaultDirName` muuttuu vain UUSILLE asennuksille.** Jo asennetut pysyvät
   `...\scan2bim`-polussa ja self-updaavat siellä (replace_app_dir käyttää `app_dir()` =
   exen oma hakemisto, ei kovakoodattua polkua) → ei riku. Uudet asentuvat `...\Ordinate`.
   Kaksi polkua rinnan on ok.
4. **Siirtymäjulkaisu:** ensimmäinen Ordinate-brändätty release kannattaa tehdä
   normaalina self-update-releasena (zip + Setup) `scan2bim-web`:iin → vanhat asennukset
   päivittyvät hiljaa Ordinate-käyttöliittymään ilman uudelleenasennusta.

---

## 4. Suoritusjärjestys (kun portti vihreä)

1. **Brändivakio:** luo `src/scan2bim/_brand.py` (`APP_NAME`, `APP_TAGLINE`), korvaa
   kovakoodatut GUI-merkkijonot viittauksilla. (1 commit, testit vihreä.)
2. **Ikoni + logo:** uusi `assets/ordinate.ico` + brand.py-piirros + sivun logo/favicon.
3. **Installer + version_info:** AppName/URLit/ryhmä → Ordinate; exe-kohde pysyy scan2bim.exe.
4. **README + website-sisältö** → Ordinate (repo-nimi ennallaan).
5. **Build + siirtymärelease** `scan2bim-web`:iin (zip+Setup, kiinteänimi Setup päivitetty).
6. (Myöhemmin, valinnainen §1c) paketti/exe/repo-rename siirtymä-updaterilla.

---

## 5. Validointi (Definition of Done)

- [ ] Kaikki testit vihreä (`pytest`).
- [ ] Build onnistuu; exe käynnistyy; ikkunaotsikko + logo lukevat **Ordinate**.
- [ ] exen ominaisuudet (oikea klikkaus → Ominaisuudet) näyttävät Ordinate.
- [ ] **Self-update-savutesti:** asenna EDELLINEN scan2bim-versio, julkaise Ordinate-
      siirtymärelease, varmista että vanha asennus päivittyy hiljaa (extract_zip löytää
      scan2bim.exe:n, replace_app_dir vaihtaa, käynnistyy Ordinate-brändättynä).
- [ ] Sivun download-linkki lataa uuden Setupin; itsepäivitys hakee zipin.
- [ ] Ei jäljellä käyttäjälle näkyvää "scan2bim"-merkkijonoa (GUI/installer/sivu/README).
- [ ] `grep -rn "scan2bim" src/` jäljellä olevat ovat VAIN paketti/import/exe-putkitusta.

---

## 6. Rollback

Rename tehdään omassa haarassa; master pysyy scan2bim-nimisenä kunnes §5 vihreä.
Self-update on turvallinen: koska exe-nimi ja repo eivät muutu, huono Ordinate-release
voidaan korvata seuraavalla releasella samaan `scan2bim-web`:iin normaalisti — vanhat
asennukset päivittyvät korjattuun. Ei umpikujaa.

---

## 7. Tiivistelmä yhdellä lauseella

**Nimetään uudelleen kaikki mitä asiakas näkee (GUI, ikoni, installer, sivu, README) →
Ordinate; pidetään näkymätön putkitus (Python-paketti `scan2bim`, `scan2bim.exe`,
`scan2bim-web`-repo) ennallaan, koska niiden vaihto rikkoisi self-updaten tai on pelkkää
churnia — ja tehdään se vasta kun domain + tavaramerkki ovat lukossa.**

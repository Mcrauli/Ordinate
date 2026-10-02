# Kolmannen osapuolen lisenssit — ordinate

ordinate itse on **proprietary** (`pyproject.toml: license = "Proprietary"`).
Tämä tiedosto luettelee mukana toimitettavat kolmannen osapuolen osat ja niiden
ehdot. **Tiedosto on toimitettava sovelluksen mukana** (installer + zip), koska
usea lisenssi vaatii ilmoituksen säilyttämistä.

> Tämä on tekninen koonti, ei oikeudellinen lausunto. Kaupallista julkaisua
> ennen kohdat **A** ja **B** on syytä tarkistuttaa juristilla.

---

## A. Huomiota vaativat — copyleft

| Osa | Lisenssi | Mitä se vaatii |
|---|---|---|
| **IfcOpenShell** | LGPL-3.0-or-later | Dynaaminen linkitys sallii proprietary-sovelluksen, mutta käyttäjällä on oltava mahdollisuus **vaihtaa kirjasto** omaan versioonsa, ja LGPL-teksti + lähdekoodin tarjous on toimitettava. |
| **PySide6 (Qt)** | LGPL-3.0 (tai kaupallinen Qt) | Sama kuin yllä. Vaihtoehto: kaupallinen Qt-lisenssi, jolloin velvoitteet poistuvat. |
| **PyInstaller** | GPL-2.0 **+ poikkeus** | Poikkeus sallii nimenomaisesti pakatun sovelluksen jakelun **millä tahansa lisenssillä**. Velvoite syntyy vain jos bootloaderia muokataan — sitä ei ole muokattu. |

**Käytännön seuraus paketointiin:** LGPL-osien (IfcOpenShell, Qt) vaihdettavuus
toteutuu selvimmin **one-dir**-paketilla, jossa `.dll`/`.pyd`-tiedostot ovat
omina tiedostoinaan ja käyttäjä voi korvata ne. One-file-paketti (kaikki
purkautuu väliaikaishakemistoon) on tässä tulkinnanvaraisempi.

---

## B. Koulutusdatan lisenssi — koskee `models/*.onnx` ja `models/wall_verifier.json`

**Toimitettavat painot ovat LISENSSIPUHTAAT (3.8.2026):** malli on harjoitettu
UUDELLEEN ilman 3DSES:ää, joten CC BY-SA -dataa ei ole painoissa. ShareAlike-
kysymys ei enää koske tuotetta.

| Aineisto | Lisenssi | Huomio |
|---|---|---|
| **Rohbau3D** (doi:10.60776/ZWJFI4) | **CC BY 4.0** (data; koodirepo MIT) | Kaupallinen käyttö sallittu, attribuutio pakollinen. Seinätarkistin (`wall_verifier.json`) on koulutettu Rohbau3D:n sitejen 00, 01, 02, 04, 07 ja 10 labeleilla. |
| Synteettiset scenet (liiketila, monikerros, kalustetut huoneet) | oma | Ei rajoitteita. |

**Attribuutio (Rohbau3D):** RauchLukas/Rohbau3D, Open Data UniBw M,
https://doi.org/10.60776/ZWJFI4 — MIT.

Malli koulutetaan **tyhjästä** (`scripts/train_3dses_full.py --rohbau … ` ilman
`--zip`-argumenttia + `scripts/geo_ablation.py --drop-rgb`), ei esiharjoitetusta
checkpointista. Resepti: Rohbau (sitet 1,4,13) + synteettinen liiketila +
monikerros + kalustetut huoneet (`--synth-retail --synth-multistory
--synth-furnished`). Mitattu vs. aiempi 3DSES-yhdistelmämalli: rohbau-rakenne
0.947 → **0.987**, asunto/talo loppumalli ekvivalentti, asunto-pintatarkkuus
sisäseinillä ≤2.5 mm (aiempi ≤1.5 mm — pieni pysyvä ero, synteettinen ei tavoita
3DSES:n oikean kalusteen tarkkuutta; kohinan 20 mm sisällä).

**HISTORIA:** aiempi tuotantomalli (v0.9.1 asti) oli yhdistelmäkoulutettu 3DSES
(CC BY-SA) + Rohbau + synteettinen. Sen ShareAlike-ulottuvuus painoihin oli
oikeudellisesti epäselvä → poistettu uudelleenkoulutuksella v0.9.2:ssa.

**VAROITUS:** `models/README.md` ehdottaa parannuksena S3DIS-esiharjoitettujen
painojen lataamista (`yanx27/Pointnet_Pointnet2_pytorch`). **Älä tee sitä
kaupalliseen versioon** — S3DIS (Stanford 2D-3D-S) edellyttää erillistä
käyttöehtosopimusta eikä salli vapaata kaupallista jakelua. Nykyiset painot
**eivät** sisällä S3DIS-dataa; mallitiedoston nimi on historiallinen ja
harhaanjohtava.

---

## C. Portattu koodi

**Cloud2BIM** — MIT License, Copyright (c) 2025 Václav Nežerka.
`src/ordinate/core/segmentation/wall_contour.py` on portattu tästä projektista.
MIT vaatii copyright-ilmoituksen ja lisenssitekstin säilyttämisen:

```
MIT License

Copyright (c) 2025 Václav Nežerka

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

`reference/` sisältää kokonaiset kopiot Cloud2BIM- ja dwg2ifc-projekteista
kehitysviitteenä. **Niitä ei toimiteta sovelluksen mukana** eikä niitä pakata
exe:hen (`build/ordinate.spec` bundlaa vain `models/`, riippuvuudet ja koodin).

---

## D. Sallivat lisenssit (ei velvoitteita attribuutiota lukuun ottamatta)

| Osa | Lisenssi |
|---|---|
| Open3D | MIT |
| NumPy, SciPy, Shapely, laspy | BSD |
| OpenCV (`opencv-python`) | Apache-2.0 |
| ONNX Runtime | MIT |
| pydantic, ezdxf, pye57 | MIT |
| click | BSD-3-Clause |
| packaging | Apache-2.0 / BSD-2-Clause |
| cryptography (päivitysten allekirjoitus) | Apache-2.0 / BSD-3-Clause |

**Open3D:n transitiiviset riippuvuudet** (paketoituvat mukaan, koska Open3D
vetää ne web-visualisoijaansa/TensorBoard-integraatioonsa; ordinate ei käytä
niitä, mutta ne ovat toistaiseksi bundlessa):

| Osa | Lisenssi |
|---|---|
| Flask, Werkzeug, MarkupSafe, itsdangerous | BSD-3-Clause |
| plotly | MIT |
| importlib_metadata | Apache-2.0 |
| typing_extensions | PSF-2.0 |

> **Optimointimahdollisuus (ei tehty):** koska ordinate ei käytä Open3D:n
> web-visualisoijaa, nämä voi jättää pois `build/ordinate.spec`:n
> `excludes`-listalla → pienempi paketti ja vähemmän attribuutiovelvoitteita.
> Vaatii build+testin (varmista ettei Open3D tuo niitä eageristi importissa).

---

## F. Toteutussuunnitelmat kohtiin A ja B

Kumpikin on **tuntien työ**, ei pikakorjaus. Kirjattu tähän jotta ne voi ajaa
suoraan eikä suunnittelua tarvitse tehdä uudestaan.

### F1. LGPL → one-dir ilman että itsepäivitys hajoaa

Ongelma: LGPL §4(d)(1) vaatii että käyttäjä voi **vaihtaa kirjaston**. One-file
purkaa kaiken temp-hakemistoon → ei täyty. One-dir täyttää. Mutta `updater.py`
vaihtaa yhden exen paikallaan, ja se on rakennettu one-filelle.

Ratkaisu käyttää **samaa Windows-kikkaa tiedosto kerrallaan**: käytössä olevaa
tiedostoa ei voi poistaa mutta sen voi *nimetä uudelleen* — tämä pätee myös
ladattuihin DLL:iin, ei vain exeen. Asennus on per-user, joten UAC:ia ei tarvita.

1. `build/ordinate.spec`: lisää `COLLECT` → `dist/ordinate/`
2. `scripts/build_exe.ps1`: paketoi hakemisto `ordinate-<v>.zip` + `.sha256`
3. `build/installer.iss`: `Source: "..\dist\ordinate\*"; Flags: recursesubdirs`
4. `updater.py`: hyväksy `.zip`-asset, pura temppiin, **vaihda tiedosto
   kerrallaan** (olemassa oleva → `.old`, uusi tilalle), siivoa `.old`-tiedostot
   käynnistyksessä kuten nytkin (`cleanup_old_exe` yleistetään hakemistoon)

**Siirtymä vanhoista asennuksista on se riskikohta.** Vanha `_select_asset` etsii
raakaa exeä; jos uudessa julkaisussa sellaista ei ole, vanha asiakas ei näe
päivitystä lainkaan (ei kaadu, mutta jää jumiin hiljaisesti). Siksi:
**julkaise siirtymäversio jossa on SEKÄ raaka exe ETTÄ zip**, ja tee siitä
versiosta viimeinen one-file — sen exe sisältää jo zip-tietoisen updaterin,
joten seuraava päivitys siirtää käyttäjän one-diriin.

**Ennen julkaisua on testattava oikeasti:** build → asennus → päivitys vanhasta
versiosta uuteen. Tätä ei voi todentaa muuten kuin ajamalla.

Vaihtoehto joka poistaa vain Qt:n velvoitteen: kaupallinen Qt-lisenssi.
**IfcOpenShell jää silti LGPL:ksi** eikä sille ole kaupallista vaihtoehtoa, joten
one-dir tarvitaan joka tapauksessa.

### F2. 3DSES pois painoista — ✅ TEHTY (v0.9.2, 3.8.2026)

Malli koulutettu uudelleen ilman 3DSES:ää (Rohbau + synteettinen, ml. kalustetut
huoneet). Rohbau-rakenne 0.947 → 0.987, gauntlet vihreä, loppumalli ekvivalentti.
Ks. kohta B. **Alla oleva alkuperäinen suunnitelma jätetty viitteeksi.**

Aiempi tuotantomalli oli koulutettu `scripts/train_3dses_rohbau.py`:llä
("3DSES Gold + Rohbau"), eli CC BY-SA -dataa oli mukana.

1. Ympäristö: `py -3.12 -m venv .venv_train` + `pip install torch` (~2.5 GB)
2. Data: Rohbau3D (MIT) — `scripts/rohbau_download.py`. Nykyinen skripti vaatii
   `--gold`-argumentin **pakollisena**; tee Rohbau-only-polku tai käytä
   `export_s3dis_model.py --train` (puhtaasti synteettinen).
3. Koulutus + **koko gauntlet vihreänä ennen korvaamista** (AGENTS.md: asunto +
   talo35 + rohbau keep-ratet). Varmuuskopiot `models/_backup/`.
4. Vertailukohta on nykyinen malli: Rohbau-rakenne 0.947, hyllynpoisto ~71 %,
   TGA-poisto ~90 %. Uusi malli saa korvata vain jos se yltää näihin.

**Riski:** AGENTS.md:n dokumentoitu "seesaw" — pelkkä Rohbau-koulutus *tuhosi
asuntosuodatuksen* kerran. Synteettistä liiketila- ja asuntodataa on siis
pidettävä mukana.

---

## E. Markkinointikäyttö — mitä kuvista saa näyttää

| Aineisto | Saako käyttää markkinoinnissa |
|---|---|
| Rohbau3D | **Kyllä**, CC BY 4.0 + attribuutio. |
| 3DSES | Kyllä, mutta **CC BY-SA**: attribuutio pakollinen, ja johdannainen kuva voi joutua saman lisenssin alle. Turvallisinta olla käyttämättä myyntimateriaalissa. |
| Asiakas- ja omat keilaukset (`raw_scans_apartment`, `aligned_low_*`, `gargage.e57`) | **Selvitettävä erikseen.** Jos data on asiakkaan, markkinointikäyttöön tarvitaan lupa. |

**Suositus:** käytä myyntimateriaalissa **Rohbau3D:tä tai omaa keilausta** — ne
ovat juridisesti puhtaita ja Rohbau on lisäksi lähellä asiakaskohteiden tyyppiä
(iso, korkea, palkitettu runko).

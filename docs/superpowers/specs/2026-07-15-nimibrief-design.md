# Nimibrief — scan2bimin uudelleenbrändäys

**Päivä:** 2026-07-15
**Tila:** ✅ Nimi valittu — **Ordinate**. Lukitusportti (muodollinen tavaramerkki +
domain) kesken ennen varsinaista rollouttia.

## Miksi

`scan2bim` on **täysin geneerinen** ja alalla laajassa käytössä. Sitä **ei voi
suojata tavaramerkkinä** eikä sillä erotu. Rebrändäys on halvin nyt — ennen
pilotin ulkopuolista myyntiä, ennen kuin nimi on kiinni asiakassuhteissa,
domainissa, exe-nimessä ja dokumenteissa. Nimi on myös osa IP-tarinaa (oma koodi,
ei "wrapperi") jota geneerinen nimi vesittää. Pilotti Radikalille voi pyöriä
sisäisesti nykynimellä; nimi lukitaan **ennen laajempaa lanseerausta**.

## Suunta (päätetty)

| Akseli | Valinta |
|---|---|
| Tyyli | Mielikuva / metafora |
| Kieli | Kansainvälinen / neutraali (toimii englanniksi) |
| Suhde dwg2ifc:hen | Oma itsenäinen brändi |
| Mielikuva | Rakenne / perusta / mittausreferenssi |

## Valittu nimi: **Ordinate**

- **Mielikuva:** koordinaattiakseli (y-ordinaatta) — mittaus, koordinaatit,
  tarkkuus. Osuu suoraan tuotteen ytimeen: mm-tarkka malli oikeissa
  koordinaateissa (juuri se georef-työ, IfcMapConversion, jonka teimme).
- **Vahvuudet:** puhdas AEC/BIM-vertikaalissa, tekninen ja uskottava, lyhyt,
  äänneasu toimii englanniksi ja suomeksi.
- **Tavaramerkki:** ei löytynyt aktiivista *Ordinate*-ohjelmistotavaramerkkiä
  luokissa 9/42. Ainoa tunnettu "Ordinate" (Ordinate Corp, puheentunnistustestit)
  on eri luokka ja käytännössä lakannut (sulautui Pearson/Versantiin). → ei
  näkyviä esteitä; **muodollinen EUIPO+PRH-haku on silti lukitusportti**.
- **Domainit (RDAP, vahvistettava rekisteröijällä):**
  - Vapaalta vaikuttaa: **ordinate.io**, **ordinate.fi**, ordinate.co,
    ordinateapp.com, useordinate.com, ordinatebim.com
  - Varattu: ordinate.com, ordinate.app/.dev/.tech/.ai, getordinate.com,
    tryordinate.com
  - **Suositeltu: `ordinate.io` (kansainvälinen) tai `ordinate.fi` (kotimainen).**

## Törmäystarkistuksen tulokset (kaikki kandidaatit)

| Nimi | Verdikti | Syy |
|---|---|---|
| **Ordinate** | ✅ VALITTU | Puhdas vertikaalissa, osuu ytimeen, TM auki, domain työstettävissä |
| Monument | 🟢 varalla | Puhdas AEC:ssä (vain hautakivi-ohjelmistot), vahva kaksoismerkitys |
| Plinth | 🟢 varalla | Puhdas, perusta-metafora, erottuva |
| Plumb | 🟡 hylätty | Vapaa mutta vahva putkiala-assosiaatio sotkee |
| Traverse | 🟡 hylätty | **Traverse PC** = survey-ohjelmisto samassa kategoriassa |
| Datum | 🔴 hylätty | **Autodesk Datum** + **Datumate/DatuBIM** + **Datum Tech (scan-to-BIM)** |
| Ashlar | 🔴 hylätty | **Ashlar-Vellum** = vakiintunut CAD/3D-ohjelmisto |
| Joist | 🔴 hylätty | **Joist Inc.** = urakoitsijoiden laskutus-appi |

## Lukitusportti (ennen rollouttia)

- [ ] **Muodollinen tavaramerkkihaku** EUIPO eSearch plus + PRH, luokat **9** ja
      **42** ("Ordinate" + samankaltaiset). Tämä on lopullinen este.
- [ ] **Rekisteröi domain** — `ordinate.io` ja/tai `ordinate.fi` (varmista ensin
      RDAP-tulos rekisteröijällä).
- [ ] (Valinnainen) some-käyttäjänimet LinkedIn/X.

## Rollout-suunnitelma (kun portti vihreä)

Järjestys, pienimmästä riskistä suurimpaan — **ei aloiteta ennen kuin nimi lukittu:**

1. **Domain + tavaramerkki** kuntoon (yllä).
2. **Sisäinen/koodi:** paketin/exe:n nimi, `_version.py`-metatiedot, GUI-otsikko,
   README/AGENTS/CHANGELOG. Pipeline-koodi (`scan2bim`-paketti) voi säilyä
   sisäisenä nimenä tai vaihtua — päätettävä (iso mekaaninen muutos).
3. **Julkinen ilme:** nettisivu (scan2bim-web → uusi domain/otsikko/logo),
   release-repo, GitHub-organisaatio/repo-nimet.
4. **Sisartuote:** päätä pysyykö dwg2ifc erillään vai tuleeko kattobrändi.

**HUOM (hard-to-reverse):** repo/organisaatio/domain-nimien vaihto ja julkinen
lanseeraus ovat ulospäin näkyviä ja vaikeasti peruttavia → tehdään vasta kun
tavaramerkki + domain on varmistettu, ja vaiheittain.

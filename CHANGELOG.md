# Muutosloki

Versiointi: `vMAJOR.MINOR.PATCH`. Releaset julkaistaan
[`Mcrauli/scan2bim-web`](https://github.com/Mcrauli/scan2bim-web/releases):iin;
sovellus päivittää itsensä sieltä.

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

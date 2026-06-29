# Muutosloki

Versiointi: `vMAJOR.MINOR.PATCH`. Releaset julkaistaan
[`Mcrauli/scan2bim-web`](https://github.com/Mcrauli/scan2bim-web/releases):iin;
sovellus päivittää itsensä sieltä.

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

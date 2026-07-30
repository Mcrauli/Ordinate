# PointNet-kalustesuodatin (Vaihe 2)

`s3dis_pointnet.onnx` — per-piste-semanttinen segmentointimalli joka luokittelee
pistepilven pisteet 13 S3DIS-luokkaan. Pipeline pitää rakenneluokat (0–6) ja
poistaa kalusteet/krääsän (7–12) ennen geometrista putkea.

Bundlataan exe:hen automaattisesti (`build/scan2bim.spec`).

## Tiedostot

| Tiedosto | Kuvaus |
|---|---|
| `s3dis_pointnet.onnx` | Inferenssimalli (CPU, ONNX Runtime). Tämä bundlataan exe:hen. |
| `s3dis_pointnet.pth` | PyTorch-checkpoint. Uudelleenvientiin ilman uutta harjoitusta. |

## Miten tämä tehtiin

Harjoitettu 3DSES TLS-skannidatalla (Zenodo 13323342, ~20M pistettä oikeasta
sisätilaskannauksesta). Labelit generoitiin geometrisesti (lattia/katto z-piikeistä,
seinät täyskorkuisista XY-kolumneista, muu = kaluste), harvennettu 30 mm voxeliin,
poimittu 1 m × 1 m lohkoihin (4096 pistettä/lohko, 50 % limitys), 60 epokkia.

Uudelleentuotto:
```
python scripts/export_s3dis_model.py --train --data <labeled_npy_dir>
```

## Validointi (S170, 40 lohkoa, 164k pistettä)

- Rakenne säilyy: **98.9 %** (seinä/lattia/katto ei tuhoudu)
- Kaluste tunnistetaan: **48 %**
- Yleistarkkuus: **98.3 %**

Malli on tarkoituksella varovainen — poistaa vain varmat kalusteet, ei koske
rakenteisiin. Toimii geometrisen pystymaskin LISÄNÄ, ei tilalle.

## Lisenssi — LUE ENNEN KOULUTUSTA

Tiedostonimi on **harhaanjohtava**: painoissa **ei ole S3DIS-dataa**, vain
S3DIS:n luokkataksonomia (13 luokkaa). Koulutusaineistot ja niiden ehdot:

| Aineisto | Lisenssi | Seuraus |
|---|---|---|
| 3DSES (Zenodo 13323342) | **CC BY-SA 4.0** | kaupallinen käyttö ok, **attribuutio pakollinen**, ShareAlike tulkinnanvarainen mallipainoille |
| Rohbau3D (doi:10.60776/ZWJFI4) | MIT | vapaa |
| synteettiset scenet | oma | vapaa |

Jos ShareAlike halutaan pois, harjoita ilman 3DSES:ää — Rohbau (MIT) +
synteettinen riittävät. Ks. `THIRD-PARTY-NOTICES.md` kohta B.

> **ÄLÄ lataa S3DIS-esiharjoitettuja painoja kaupalliseen versioon.**
> S3DIS (Stanford 2D-3D-S) vaatii erillisen käyttöehtosopimuksen eikä salli
> vapaata kaupallista jakelua. Aiempi versio tästä tiedostosta ehdotti
> `yanx27/Pointnet_Pointnet2_pytorch`-painojen käyttöä kaluste-recallin
> parantamiseksi — se saastuttaisi tuotteen juridisesti. Käytä sen sijaan
> lisää Rohbau-sceneja tai synteettistä dataa.

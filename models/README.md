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

## Parannus

Parempi kaluste-recall vaatii oikeat S3DIS-esiharjoitetut painot:
```
# Lataa best_model.pth: github.com/yanx27/Pointnet_Pointnet2_pytorch
python scripts/export_s3dis_model.py --weights best_model.pth
```

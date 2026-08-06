"""MobileSAM (Apache-2.0) luokka-agnostinen segmentointi onnxruntimella — EI torchia.

Työkalu treenidatan LABELOINTIIN (ei tuotteeseen): SAM segmentoi skannerikuvat
puhtaiksi alueiksi, joille annetaan luokka geometrialla (takaisinprojisointi:
alue seinätasolla = seinä, edessä = kaluste). Lisenssipuhdas: SAM:n PAINOT ovat
Apache-2.0 (kaupallinen-OK), toisin kuin sisätiladatasetit (S3DIS/ADE20K/ScanNet
= ei-kaupallisia).

Mallit (gitignore, lataa kerran):
  models/mobilesam/enc.onnx  (28 MB)  MobileSAM TinyViT-encoder
  models/mobilesam/dec.onnx  (16 MB)  SAM-decoder
  Lähde: huggingface.co/PulpCut/mobilesam-onnx (mobilesam.encoder/decoder.onnx)

Validoitu resepti (scratchpad/samdbg.py): encoder ottaa RAAKA 0-255 HWC-kuvan
(bakettaa preprocessingin sisäisesti — ImageNet-normalisointi ITSE ylinormalisoi).
Decoder: yksi maski/prompt. Automaattimaskit = pisteruudukko + IoU-NMS.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

_ENC = Path("models/mobilesam/enc.onnx")
_DEC = Path("models/mobilesam/dec.onnx")


class MobileSAM:
    def __init__(self, enc_path: Path = _ENC, dec_path: Path = _DEC, size: int = 1024):
        self.size = size
        self.enc = ort.InferenceSession(str(enc_path), providers=["CPUExecutionProvider"])
        self.dec = ort.InferenceSession(str(dec_path), providers=["CPUExecutionProvider"])

    def embed(self, rgb: np.ndarray) -> np.ndarray:
        """rgb HxWx3 uint8 → image_embeddings. Encoder ottaa RAAKA 0-255 (neliö 1024)."""
        inp = cv2.resize(rgb, (self.size, self.size)).astype(np.float32)
        return self.enc.run(None, {"input_image": inp})[0]

    def mask_at(self, emb: np.ndarray, x: float, y: float) -> tuple[np.ndarray, float]:
        """Yksi maski pisteprompille (koordinaatit 1024-kehyksessä). → (bool-maski, iou)."""
        out = self.dec.run(None, {
            "image_embeddings": emb,
            "point_coords": np.array([[[x, y]]], np.float32),
            "point_labels": np.array([[1]], np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), np.float32),
            "has_mask_input": np.array([0], np.float32),
            "orig_im_size": np.array([self.size, self.size], np.float32),
        })
        return out[0][0][0] > 0, float(out[1][0][0])

    def segment_everything(self, rgb: np.ndarray, grid: int = 16,
                           min_cov: float = 0.002, max_cov: float = 0.4,
                           iou_min: float = 0.85, nms_iou: float = 0.7) -> list[np.ndarray]:
        """Automaattimaskit pisteruudukolla + IoU-NMS. Maskit 1024x1024-kehyksessä."""
        emb = self.embed(rgb)
        S = self.size
        cand = []
        for gy in np.linspace(60, S - 60, grid):
            for gx in np.linspace(60, S - 60, grid):
                mk, iou = self.mask_at(emb, gx, gy)
                c = mk.mean()
                if min_cov < c < max_cov and iou > iou_min:
                    cand.append((mk, iou))
        cand.sort(key=lambda t: -t[1])
        kept: list[np.ndarray] = []
        for mk, _ in cand:
            if all((mk & k).sum() / max((mk | k).sum(), 1) <= nms_iou for k in kept):
                kept.append(mk)
        return kept


if __name__ == "__main__":
    import sys
    sam = MobileSAM()
    img = cv2.cvtColor(cv2.imread(sys.argv[1]), cv2.COLOR_BGR2RGB)
    masks = sam.segment_everything(img)
    print(f"{len(masks)} aluetta")

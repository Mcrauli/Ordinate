"""Semanttinen kalustesuodatin — PointNet ONNX (Vaihe 2, Step 1 jää fallbackiksi).

Pistepilvi jaetaan 1 m × 1 m lohkoihin (500 mm stride, 50 % overlap).
Jokaiselle lohkolle ajetaan S3DIS-harjoitettu PointNet ONNX-malli joka antaa
per-piste-luokat (13 S3DIS-luokkaa). Rakenteelliset luokat 0–6 säilytetään,
kaluste-/krääsäluokat 7–12 poistetaan.

Mallin polku:
  exe:  sys._MEIPASS / models / s3dis_pointnet.onnx
  dev:  <repo_root> / models / s3dis_pointnet.onnx

Jos malli tai onnxruntime puuttuu, käytetään geometristä SemanticFilter-fallbackia.
Mallin luonti: scripts/export_s3dis_model.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

log = logging.getLogger(__name__)

_MODEL_FILENAME = "s3dis_pointnet.onnx"

# S3DIS 13 luokkaa: 0-6 rakenteellisia, 7-12 kalusteet/krääsä
_KEEP_CLASSES: frozenset[int] = frozenset(range(7))  # ceiling,floor,wall,beam,column,window,door

# Lohkoprosessoinnin parametrit (mm)
_BLOCK_SIZE   = 1000.0   # lohkon sivun pituus
_BLOCK_STRIDE =  500.0   # ruudukon askel (50 % overlap)
_N_BLOCK_PTS  = 4096     # pisteitä per lohko (vastattava mallin odottamaa)
_N_FEATURES   = 9        # xyz_local + xyz_scene + rgb_zeros
_N_CLASSES    = 13

# Työ-voxel äänestystä varten
_WORK_VOXEL = 30.0       # mm


def _find_model_path() -> Path | None:
    """Palauttaa mallin polun tai None jos ei löydy."""
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "models" / _MODEL_FILENAME  # type: ignore[attr-defined]
        return p if p.exists() else None

    # Dev: kävele ylös kunnes löytyy pyproject.toml (repo root)
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            p = candidate / "models" / _MODEL_FILENAME
            return p if p.exists() else None
    return None


class PointNetFilter:
    """S3DIS PointNet ONNX -kalustesuodatin. Fallback geometriseen jos malli puuttuu."""

    def __init__(self, model_path: Path | None = None) -> None:
        path = model_path or _find_model_path()
        self._session = self._load_session(path)
        if self._session is not None:
            log.debug("PointNetFilter: malli ladattu %s", path)
        else:
            log.info("PointNetFilter: ONNX-mallia ei löydy, käytetään geometristä fallbackia")

    @staticmethod
    def _load_session(path: Path | None):
        if path is None:
            return None
        try:
            import onnxruntime as ort  # noqa: PLC0415
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 4
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            return ort.InferenceSession(
                str(path),
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            log.warning("PointNetFilter: onnxruntime lataus epäonnistui: %s", exc)
            return None

    def is_available(self) -> bool:
        """True jos ONNX-malli on ladattu (ei geometrinen fallback)."""
        return self._session is not None

    def filter(self, cloud: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
        """Palauttaa pilven josta kalusteet/krääsä on poistettu."""
        if self._session is None:
            from .semantic_filter import SemanticFilter  # noqa: PLC0415
            return SemanticFilter().filter(cloud)

        pts_full = np.asarray(cloud.points)
        if len(pts_full) < 1000:
            return cloud

        keep = self._classify(pts_full)
        if keep.sum() < 200:
            return cloud

        return cloud.select_by_index(np.where(keep)[0])

    # -----------------------------------------------------------------------

    def _classify(self, pts_full: np.ndarray) -> np.ndarray:
        """Palauttaa boolean-maskin: True = rakenteellinen piste."""
        # Työ-voxel: normalisoi pistemäärä → nopea lohkoprosessointi
        origin = pts_full.min(axis=0)
        wc = o3d.geometry.PointCloud()
        wc.points = o3d.utility.Vector3dVector(pts_full)
        wc = wc.voxel_down_sample(_WORK_VOXEL)
        wpts = np.asarray(wc.points)
        if len(wpts) < 64:
            return np.ones(len(pts_full), dtype=bool)

        # Skene-tason normalisointi (0–1 koko pilven yli)
        sc_min = wpts.min(axis=0)
        sc_max = wpts.max(axis=0)
        sc_range = np.maximum(sc_max - sc_min, 1.0)

        votes = np.zeros((len(wpts), _N_CLASSES), dtype=np.float32)
        input_name = self._session.get_inputs()[0].name

        x_starts = np.arange(sc_min[0], sc_max[0] + 1.0, _BLOCK_STRIDE)
        y_starts = np.arange(sc_min[1], sc_max[1] + 1.0, _BLOCK_STRIDE)

        for xs in x_starts:
            for ys in y_starts:
                in_block = (
                    (wpts[:, 0] >= xs) & (wpts[:, 0] < xs + _BLOCK_SIZE) &
                    (wpts[:, 1] >= ys) & (wpts[:, 1] < ys + _BLOCK_SIZE)
                )
                idx = np.where(in_block)[0]
                if len(idx) < 32:
                    continue

                n = len(idx)
                block_pts = wpts[idx]

                # Näytteidenotto: sample tai pad → N_BLOCK_PTS
                if n >= _N_BLOCK_PTS:
                    sel = np.random.choice(n, _N_BLOCK_PTS, replace=False)
                else:
                    sel = np.concatenate([
                        np.arange(n),
                        np.random.choice(n, _N_BLOCK_PTS - n),
                    ])
                sampled = block_pts[sel]

                # 9 piirrettä: xyz_local (0-1 lohkossa) + xyz_scene (0-1 skenessä) + rgb=0
                feat = np.zeros((_N_BLOCK_PTS, _N_FEATURES), dtype=np.float32)
                feat[:, 0] = (sampled[:, 0] - xs) / _BLOCK_SIZE
                feat[:, 1] = (sampled[:, 1] - ys) / _BLOCK_SIZE
                feat[:, 2] = (sampled[:, 2] - sc_min[2]) / sc_range[2]
                feat[:, 3] = (sampled[:, 0] - sc_min[0]) / sc_range[0]
                feat[:, 4] = (sampled[:, 1] - sc_min[1]) / sc_range[1]
                feat[:, 5] = (sampled[:, 2] - sc_min[2]) / sc_range[2]
                # feat[:, 6:9] = 0  # rgb — ei väridataa pistepilvessä

                inp = feat[np.newaxis]  # (1, N_BLOCK_PTS, 9)
                logits = self._session.run(None, {input_name: inp})[0]  # (1, N_BLOCK_PTS, 13)
                probs = _softmax(logits[0])  # (N_BLOCK_PTS, 13)

                # Kasaa äänet takaisin työ-voxeli-indekseihin (np.add.at käsittelee toistot)
                wpts_idx = idx[sel]
                np.add.at(votes, wpts_idx, probs)

        # Pisteet ilman yhtään ääntä (reunat, ei lohkossa) → pidä
        no_vote = votes.sum(axis=1) == 0
        pred = votes.argmax(axis=1)
        structural = np.isin(pred, list(_KEEP_CLASSES))
        structural[no_vote] = True

        # Siirrä maski täydelle pilvelle voxel-grid-hashilla
        def _vkey(p: np.ndarray) -> np.ndarray:
            v = np.floor((p - origin) / _WORK_VOXEL).astype(np.int64)
            return (v[:, 0] * 100_003 + v[:, 1]) * 100_003 + v[:, 2]

        kept_keys = np.unique(_vkey(wpts[structural]))
        return np.isin(_vkey(pts_full), kept_keys)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)

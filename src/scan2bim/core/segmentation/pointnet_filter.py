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
_MODEL_FILENAME_RETAIL = "s3dis_pointnet_retail.onnx"   # liiketila/tyomaa-variantti
                                                        # (hyllynpoisto 95% vs 17%;
                                                        # asuntokaytossa oletusmalli on tarkempi)

# S3DIS 13 luokkaa: 0-6 rakenteellisia, 7-12 kalusteet/krääsä
_KEEP_CLASSES: frozenset[int] = frozenset(range(7))  # ceiling,floor,wall,beam,column,window,door
_RM_CLASSES: list[int] = list(range(7, 13))          # table,chair,sofa,bookcase,board,clutter

# Lohkoprosessoinnin parametrit (mm)
_BLOCK_SIZE   = 1000.0   # lohkon sivun pituus
_BLOCK_STRIDE =  500.0   # ruudukon askel (50 % overlap)
_N_BLOCK_PTS  = 4096     # pisteitä per lohko (vastattava mallin odottamaa)
_N_FEATURES   = 9        # xyz_local + xyz_scene + rgb_zeros (vanha malli)
_N_CLASSES    = 13

# Uudemmat XYZ-only-mallit korvaavat rgb-nollat lasketuilla piirteillä:
#   9  = base6 + rgb-nollat                    (alkuperäinen)
#   13 = base6 + korkeus + geo(3) + sarake(3)  (väritön, piirteet skenestä)
# Kanavamäärä luetaan ONNX-mallista, joten sama koodi ajaa molempia eikä
# nykyinen tuotantomalli muuta käytöstään.
_N_FEATURES_GEOCOL = 13

# Työ-voxel äänestystä varten
_WORK_VOXEL = 30.0       # mm
_INFER_BATCH = 64        # lohkoa per ONNX-kutsu (nopeus; ei laatuvaikutusta)
_KEY_CHUNK = 4_000_000   # pistettä per erä ruudukkoavainta laskettaessa


def _voxel_keys(pts: np.ndarray, origin: np.ndarray) -> np.ndarray:
    """Per-piste avain _WORK_VOXEL-ruudukkoon, erissä.

    Koko pilvelle kerralla laskettuna lauseke varaa neljä pilven kokoista
    float64-välivaihetta (vähennys, jako, floor, astype) — 31 M pisteellä ~3 GB
    pelkkää transienttia. Erissä laskettuna tulos on BITILLEEN sama, koska
    jokainen piste käy läpi täsmälleen saman lausekkeen; vain välivaiheen koko
    on rajattu."""
    out = np.empty(len(pts), dtype=np.int64)
    for lo in range(0, len(pts), _KEY_CHUNK):
        hi = min(lo + _KEY_CHUNK, len(pts))
        v = np.floor((pts[lo:hi] - origin) / _WORK_VOXEL).astype(np.int64)
        out[lo:hi] = (v[:, 0] * 100_003 + v[:, 1]) * 100_003 + v[:, 2]
    return out


def _find_model_path(variant: str = "default") -> Path | None:
    """Palauttaa mallin polun tai None jos ei löydy."""
    fname = _MODEL_FILENAME_RETAIL if variant == "retail" else _MODEL_FILENAME
    if getattr(sys, "frozen", False):
        p = Path(sys._MEIPASS) / "models" / fname  # type: ignore[attr-defined]
        return p if p.exists() else None

    # Dev: kävele ylös kunnes löytyy pyproject.toml (repo root)
    candidate = Path(__file__).resolve()
    for _ in range(8):
        candidate = candidate.parent
        if (candidate / "pyproject.toml").exists():
            p = candidate / "models" / fname
            return p if p.exists() else None
    return None


S3DIS_WALL = 2       # luokkaindeksi: 0=ceiling 1=floor 2=wall 3=beam 4=column …


class SemanticLabels:
    """Semanttiset luokat 30 mm ruudukkoon avainnettuna.

    Taulukkomuotoiset labelit eivät kestä uudelleenharvennusta (detektori
    voxeloi ison pilven omalla koollaan) — ruudukkoavain kestää."""

    __slots__ = ("_origin", "_voxel", "_keys", "_labels")

    def __init__(self, origin, voxel, keys, labels) -> None:
        self._origin = origin
        self._voxel = voxel
        self._keys = keys
        self._labels = labels

    @classmethod
    def build(cls, pts: np.ndarray, pred: np.ndarray) -> "SemanticLabels":
        origin = pts.min(axis=0)
        key = _voxel_keys(pts, origin)
        uniq, first = np.unique(key, return_index=True)
        return cls(origin, _WORK_VOXEL, uniq, pred[first].astype(np.int8))

    def lookup(self, pts: np.ndarray) -> np.ndarray:
        """Per-piste luokka; -1 kun voxelia ei ole nähty."""
        vox = np.floor((np.asarray(pts) - self._origin) / self._voxel).astype(np.int64)
        key = (vox[:, 0] * 100_003 + vox[:, 1]) * 100_003 + vox[:, 2]
        pos = np.searchsorted(self._keys, key)
        pos = np.clip(pos, 0, len(self._keys) - 1)
        hit = self._keys[pos] == key
        out = np.full(len(key), -1, dtype=np.int8)
        out[hit] = self._labels[pos[hit]]
        return out


class PointNetFilter:
    """S3DIS PointNet ONNX -kalustesuodatin. Fallback geometriseen jos malli puuttuu."""

    def __init__(self, model_path: Path | None = None, variant: str = "default",
                 removal_bias: float = 0.0) -> None:
        """removal_bias siirtää operointipistettä: lisätään poistoluokkien
        logiteihin ennen softmaxia. 0 = mallin oma piste (oletus, ei muutosta),
        suurempi = poistaa enemmän mutta säilyttää vähemmän rakennetta.
        Malleja saa verrata vain SAMALLA rakennetasolla, ei tällä arvolla."""
        path = model_path or _find_model_path(variant)
        if path is None and variant != "default":
            path = _find_model_path()   # retail-mallia ei bundlattu → oletusmalli
        self._session = self._load_session(path)
        self._n_features = _session_n_features(self._session)
        self._removal_bias = float(removal_bias)
        if self._session is not None:
            log.debug("PointNetFilter: malli ladattu %s (%d piirrettä)", path, self._n_features)
        else:
            log.info("PointNetFilter: ONNX-mallia ei löydy, käytetään geometristä fallbackia")

    @staticmethod
    def _load_session(path: Path | None):
        if path is None:
            return None
        try:
            import os  # noqa: PLC0415
            import onnxruntime as ort  # noqa: PLC0415
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = min(os.cpu_count() or 4, 8)
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
        # Laattakaistat pakkosäilytetään: lattia/katto ovat z-histogrammin
        # dominantit piikit eikä niiden poisto ole koskaan oikein (rouhea
        # holvipinta luokittui työmaalla 55 % roskaksi → slab/perimetri
        # menettäisi evidenssin). Malli päättää vain kaistan ULKOpuolelta.
        keep |= _slab_bands(pts_full)
        if keep.sum() < 200:
            return cloud

        return cloud.select_by_index(np.where(keep)[0])

    # -----------------------------------------------------------------------

    def filter_with_labels(self, cloud: o3d.geometry.PointCloud):
        """Suodatettu pilvi + semanttiset labelit SAMALLA inferenssillä.

        Palauttaa (cloud, SemanticLabels|None). Labelit avainnetaan 30 mm
        ruudukkoon, jotta ne kohdistuvat vaikka detektori harventaisi pilven
        uudelleen omalla voxelillaan."""
        if self._session is None:
            return self.filter(cloud), None
        pts_full = np.asarray(cloud.points)
        if len(pts_full) < 1000:
            return cloud, None

        res = self._classify_voxels(pts_full)
        if res is None:
            return cloud, None
        pred_vox, origin, uniq, inv = res
        # Labelit SAMASTA ruudukosta jonka inferenssi jo laski. Aiemmin tässä
        # kutsuttiin SemanticLabels.build(pts_full, pred), joka rakensi
        # identtisen ruudukon toiseen kertaan koko pilvelle — turha täysi
        # läpikäynti ison skannin muistihuipun päälle.
        labels = SemanticLabels(origin, _WORK_VOXEL, uniq, pred_vox)
        keep = (np.isin(pred_vox, list(_KEEP_CLASSES)) | (pred_vox < 0))[inv]
        keep |= _slab_bands(pts_full)
        if keep.sum() < 200:
            return cloud, labels
        return cloud.select_by_index(np.where(keep)[0]), labels

    def predict_classes(self, pts_full: np.ndarray) -> np.ndarray | None:
        """Per-piste S3DIS-luokka (0=ceiling,1=floor,2=wall,3=beam,4=column,
        5=window,6=door,7..12=kalusteet). None jos mallia ei ole.

        Malli erottaa seinän ja palkin toisistaan; `filter` heittää sen tiedon
        pois ja palauttaa vain keep/remove. Ulos annettuna sitä voi käyttää
        siellä missä geometria joutuisi päättelemään saman uudestaan."""
        if self._session is None or len(pts_full) < 1000:
            return None
        return self._classify(pts_full, return_pred=True)

    def _classify(self, pts_full: np.ndarray, return_pred: bool = False) -> np.ndarray:
        """Palauttaa boolean-maskin: True = rakenteellinen piste.

        return_pred=True → palauttaa sen sijaan per-piste luokkaindeksin."""
        res = self._classify_voxels(pts_full)
        if res is None:
            return np.ones(len(pts_full), dtype=bool)
        pred_vox, _origin, _uniq, inv = res
        if return_pred:
            return pred_vox[inv]
        # Piste perii oman voxelinsa päätöksen. Äänettömät voxelit (pred -1,
        # reunalohkot) pidetään.
        return (np.isin(pred_vox, list(_KEEP_CLASSES)) | (pred_vox < 0))[inv]

    def _classify_voxels(self, pts_full: np.ndarray):
        """Per-VOXEL luokka + ruudukko: (pred_vox, origin, uniq, inv) tai None.

        pred_vox on int8, -1 = ei yhtään ääntä. Sekä maski, per-piste-luokat
        että SemanticLabels johdetaan tästä yhdestä läpikäynnistä."""
        # Deterministinen näytteistys: sama syöte → sama malli joka ajolla.
        # Globaali np.random heilutti seinien pintalukitusta ±6mm ajojen välillä.
        rng = np.random.RandomState(0)
        # Työ-voxel OMALLA gridillä (ei o3d voxel_down_sample): o3d:n grid on
        # ankkuroitu eri origoon → sentroidi voi pudota eri soluun kuin
        # lähdepisteensä, jolloin avainpohjainen maskinsiirto hukkaa
        # tasopinnoilta ~20–30 % pisteistä (mitattu: Wall 89 % → 66 %).
        # Sama grid molempiin suuntiin = jokainen piste perii täsmälleen
        # oman voxelinsa päätöksen.
        origin = pts_full.min(axis=0)
        vkey = _voxel_keys(pts_full, origin)
        # vuniq, EI uniq: alempana lohkoruudukko käyttää nimeä uniq omiin
        # ruutu-id:ihinsä ja ylikirjoittaisi nämä voxeliavaimet.
        vuniq, first, inv = np.unique(vkey, return_index=True, return_inverse=True)
        # vkey on kuollut heti unique:n jälkeen mutta jäisi elämään funktion
        # loppuun asti — 31 M pisteellä 0.25 GB koko inferenssisilmukan ajan.
        del vkey
        wpts = pts_full[first]
        del first          # sama: tarvitaan vain wpts:n poimintaan
        if len(wpts) < 64:
            return None

        # Skene-tason normalisointi (0–1 koko pilven yli)
        sc_min = wpts.min(axis=0)
        sc_max = wpts.max(axis=0)
        sc_range = np.maximum(sc_max - sc_min, 1.0)

        votes = np.zeros((len(wpts), _N_CLASSES), dtype=np.float32)
        input_name = self._session.get_inputs()[0].name

        # Skenetason piirteet kerran koko pilvelle — EI per lohko: sarakkeen
        # täyttöaste kertoo ulottuuko pinta lattiasta kattoon, mitä 1 m lohko
        # ei voi nähdä. Sama laskenta kuin koulutuksessa, samalla
        # voxeliharvennuksella (30 mm = koulutuksen 0.03 m).
        scene_extra = None
        if self._n_features == _N_FEATURES_GEOCOL:
            from . import point_features as pf  # noqa: PLC0415
            scene_extra = np.column_stack([
                pf.height(wpts),
                pf.geometric(wpts),
                pf.column(wpts),
            ]).astype(np.float32)

        x_starts = np.arange(sc_min[0], sc_max[0] + 1.0, _BLOCK_STRIDE)
        y_starts = np.arange(sc_min[1], sc_max[1] + 1.0, _BLOCK_STRIDE)

        # Lohkojako spatiaalisella ämpärikäytöllä, EI täyshaulla per lohko: iso
        # skanni (esim. 110×29 m → 13000 lohkoa) × koko wpts-täyshaku on
        # O(lohkot×pisteet) = kymmeniä miljardeja operaatioita → minuutteja
        # "jumia". Kukin piste kuuluu STRIDE-ruutuunsa; lohko (BLOCK_SIZE =
        # cpb×STRIDE) kattaa cpb×cpb ruutua. Kerää lohkon pisteet ruuduista →
        # per-lohko O(cpb²) haku. Indeksit lajitellaan nousevaan järjestykseen
        # → identtinen np.where(in_block):n kanssa (sama otanta, sama tulos).
        cpb = max(1, int(round(_BLOCK_SIZE / _BLOCK_STRIDE)))
        cx = np.floor((wpts[:, 0] - sc_min[0]) / _BLOCK_STRIDE).astype(np.int64)
        cy = np.floor((wpts[:, 1] - sc_min[1]) / _BLOCK_STRIDE).astype(np.int64)
        cx_max, cy_max = int(cx.max()), int(cy.max())
        ncy = cy_max + 1
        cellid = cx * ncy + cy
        order = np.argsort(cellid, kind="stable")
        cid_sorted = cellid[order]
        uniq, starts = np.unique(cid_sorted, return_index=True)
        ends = np.append(starts[1:], len(order))
        cell_slice = {int(c): (int(s), int(e)) for c, s, e in zip(uniq, starts, ends)}
        # Vain order ja cell_slice tarvitaan silmukassa. Loput ovat kuolleita
        # mutta jäisivät funktion loppuun asti — 31 M pisteellä 1.0 GB koko
        # inferenssin ajan sen huipun päällä.
        del cx, cy, cellid, cid_sorted, uniq, starts, ends

        def _block_idx(kx: int, ky: int) -> np.ndarray | None:
            parts = []
            for ax in range(kx, min(kx + cpb, cx_max + 1)):
                for ay in range(ky, min(ky + cpb, cy_max + 1)):
                    # ax/ay rajattu dataan → pakattu cellid ei kiedo riviä yli
                    sl = cell_slice.get(ax * ncy + ay)
                    if sl is not None:
                        parts.append(order[sl[0]:sl[1]])
            if not parts:
                return None
            idx = np.concatenate(parts)
            idx.sort()
            return idx

        # Lohkot ajetaan ERISSÄ (batch) eikä yksi kerrallaan: iso skanni tuottaa
        # tuhansia lohkoja ja per-lohko session.run(batch=1) hukkaa ajan kutsu-
        # overheadiin. PointNet käsittelee lohkot toisistaan riippumatta (eval-BN
        # = kiinteät tilastot) → batchaus antaa BITTIIN saman tuloksen, vain
        # nopeammin. rng kulutetaan samassa lohkojärjestyksessä → determinismi säilyy.
        pend_feat: list[np.ndarray] = []
        pend_idx: list[np.ndarray] = []

        def _flush() -> None:
            if not pend_feat:
                return
            inp = np.stack(pend_feat, axis=0)  # (B, N_BLOCK_PTS, n_features)
            out = self._session.run(None, {input_name: inp})[0]  # (B, N_BLOCK_PTS, 13)
            for bi in range(len(pend_feat)):
                lg = out[bi]
                if self._removal_bias:
                    lg = lg.copy()
                    lg[:, _RM_CLASSES] += self._removal_bias
                np.add.at(votes, pend_idx[bi], _softmax(lg))
            pend_feat.clear()
            pend_idx.clear()

        for kx in range(len(x_starts)):
            xs = x_starts[kx]
            for ky in range(len(y_starts)):
                ys = y_starts[ky]
                idx = _block_idx(kx, ky)
                if idx is None or len(idx) < 32:
                    continue

                n = len(idx)
                block_pts = wpts[idx]

                # Näytteidenotto: sample tai pad → N_BLOCK_PTS
                if n >= _N_BLOCK_PTS:
                    sel = rng.choice(n, _N_BLOCK_PTS, replace=False)
                else:
                    sel = np.concatenate([
                        np.arange(n),
                        rng.choice(n, _N_BLOCK_PTS - n),
                    ])
                sampled = block_pts[sel]

                # base: xyz_local (0-1 lohkossa) + xyz_scene (0-1 skenessä)
                feat = np.zeros((_N_BLOCK_PTS, self._n_features), dtype=np.float32)
                feat[:, 0] = (sampled[:, 0] - xs) / _BLOCK_SIZE
                feat[:, 1] = (sampled[:, 1] - ys) / _BLOCK_SIZE
                feat[:, 2] = (sampled[:, 2] - sc_min[2]) / sc_range[2]
                feat[:, 3] = (sampled[:, 0] - sc_min[0]) / sc_range[0]
                feat[:, 4] = (sampled[:, 1] - sc_min[1]) / sc_range[1]
                feat[:, 5] = (sampled[:, 2] - sc_min[2]) / sc_range[2]
                if scene_extra is not None:
                    feat[:, 6:] = scene_extra[idx[sel]]
                # muuten feat[:, 6:9] = 0 — rgb, ei väridataa pistepilvessä

                pend_feat.append(feat)
                pend_idx.append(idx[sel])
                if len(pend_feat) >= _INFER_BATCH:
                    _flush()
        _flush()

        # Voxelit ilman yhtään ääntä (reunat, ei lohkossa) → -1
        no_vote = votes.sum(axis=1) == 0
        pred_vox = votes.argmax(axis=1).astype(np.int8)
        pred_vox[no_vote] = -1
        return pred_vox, origin, vuniq, inv


def _session_n_features(session) -> int:
    """Mallin odottama piirremäärä ONNX-syötteen viimeisestä ulottuvuudesta.

    Dynaaminen akseli (str/None) → oletetaan alkuperäinen 9-piirteinen malli.
    """
    if session is None:
        return _N_FEATURES
    dim = session.get_inputs()[0].shape[-1]
    return dim if isinstance(dim, int) and dim > 0 else _N_FEATURES


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


_SLAB_BAND_MM = 90.0     # ± piikin ympärillä
_SLAB_BIN_MM = 20.0


def _slab_bands(pts: np.ndarray) -> np.ndarray:
    """True pisteille jotka ovat dominanttien lattia/katto-z-piikkien kaistoissa."""
    z = pts[:, 2]
    z0, z1 = float(z.min()), float(z.max())
    if z1 - z0 < 500.0:
        return np.zeros(len(pts), dtype=bool)
    nbins = max(int((z1 - z0) / _SLAB_BIN_MM), 10)
    hist, edges = np.histogram(z, bins=nbins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    third = (z1 - z0) / 3.0
    mask = np.zeros(len(pts), dtype=bool)
    for lo, hi in ((z0, z0 + third), (z1 - third, z1)):
        sel = (centers >= lo) & (centers <= hi)
        if not sel.any() or hist[sel].max() == 0:
            continue
        peak_z = float(centers[sel][int(np.argmax(hist[sel]))])
        mask |= np.abs(z - peak_z) < _SLAB_BAND_MM
    return mask

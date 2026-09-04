"""Valintasaanto: mita `_best_detector` OIKEASTI maksimoi.

1555a6b vaihtoi valinnan otsikkonsa mukaan F1:een, mutta jatti voittajan
poimivan rivin ennalleen (`if cov > best_cov`). F1 paatyi vain
marginaaliportin vertailuluvuksi, jossa sita verrataan KATTAVUUTEEN —
eri yksikko. Yksikaan testi ei kattanut funktiota, joten mikaan ei kaatunut.

Diagnostiikkalokeista toistetut luvut (data/_choice_rule_replay.py) ovat
tassa sellaisenaan, jotta saannon muutos nakyy nimenomaan niissa
aineistoissa joissa se ratkaisee.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from scan2bim.core import pipeline as PL


class _Cloud:
    def __init__(self, n: int = 1000) -> None:
        self.points = np.zeros((n, 3), dtype=float)

    def voxel_down_sample(self, _v: float) -> "_Cloud":
        return self


def _slab(kind: str, z: float):
    return SimpleNamespace(slab_type=kind, elevation=z)


@pytest.fixture
def choose(monkeypatch):
    """Aja `_best_detector` kirjoitetuilla luvuilla ja palauta valitun nimi."""
    def run(scores: dict[str, tuple[float, float]], names: list[str] | None = None,
            walls: dict[str, int] | None = None) -> str:
        walls = walls or {}

        class _Model:
            def __init__(self, name: str) -> None:
                self.det_name = name
                self.walls = [object()] * walls.get(name, 1)

        class _Det:
            def __init__(self, name: str) -> None:
                self._name = name

            def detect(self, _cloud):
                return _Model(self._name)

        import scan2bim.core.qa.coverage as COV
        import scan2bim.core.segmentation.base as BASE
        import scan2bim.core.segmentation.slab_detector as SD

        monkeypatch.setattr(BASE.DetectorRegistry, "get",
                            classmethod(lambda cls, n: (lambda _n=n: _Det(_n))))
        monkeypatch.setattr(SD, "detect_slabs",
                            lambda _c: [_slab("floor", 0.0), _slab("ceiling", 3000.0)])

        seen: dict[int, str] = {}

        def _scores(_pts, walls_arg, _f, _c, *a, **k):
            return scores[seen[id(walls_arg)]]

        orig_detect = _Det.detect

        def _detect(self, cloud):
            m = orig_detect(self, cloud)
            seen[id(m.walls)] = self._name
            return m

        monkeypatch.setattr(_Det, "detect", _detect)
        monkeypatch.setattr(COV, "wall_scores", _scores)

        p = PL.Pipeline(PL.PipelineConfig(), progress=lambda _m: None)
        model, name = p._best_detector(_Cloud(), names or list(scores))
        assert model.det_name == name
        return name

    return run


def test_voittaja_on_paras_f1_ei_paras_kattavuus(choose):
    """Kattavuus on puhdas recall — maara voittaa sen aina. F1 ratkaisee."""
    assert choose({"contour": (0.30, 0.90), "histogram": (0.80, 0.10)}) == "contour"


def test_kattavuus_yksin_valitsisi_toisin(choose):
    """Sama tilanne toisin pain: F1-voittajalla saa olla PIENEMPI kattavuus."""
    assert choose({"contour": (0.90, 0.05), "histogram": (0.50, 0.50)}) == "histogram"


def test_tasapelin_ratkaisee_jarjestys(choose):
    assert choose({"contour": (0.4, 0.4), "histogram": (0.4, 0.4)}) == "contour"
    assert choose({"histogram": (0.4, 0.4), "contour": (0.4, 0.4)}) == "histogram"


def test_yksi_ehdokas_ei_mittaa_mitaan(choose):
    """Yhden nimen lista palaa suoraan — ei lattioita, ei mittausta."""
    assert choose({"normals": (0.0, 0.0)}, names=["normals"]) == "normals"


def test_marginaali_koskee_vain_uutta_menetelmaa(choose):
    """Vakiintuneet kilpailevat keskenaan ilman marginaalia."""
    assert choose({"contour": (0.30, 0.30), "histogram": (0.35, 0.35)}) == "histogram"


def test_marginaali_vertaa_f1_f1_hen(choose):
    """`normals` pudotetaan kun sen F1 ei ylita marginaalia refin F1:sta.

    Sekayksikkoinen vertailu (normalsin KATTAVUUS vs refin F1) paastaisi taman
    lapi: kattavuus 0.60 > 3 x 0.180. Yksikkojen kanssa 0.24 < 3 x 0.180.
    """
    assert choose({"contour": (0.10, 0.90), "normals": (0.60, 0.15)}) == "contour"


def test_normals_voittaa_kun_ero_on_kyllin_suuri(choose):
    assert choose({"contour": (0.05, 0.05), "normals": (0.60, 0.60)}) == "normals"


@pytest.mark.parametrize(
    "nimi, luvut, odotus",
    [
        # data/output/_matrix/*/diagnostics.txt, ajo 2026-09-03
        ("kellari", {"contour": (0.046, 0.263), "histogram": (0.058, 0.012),
                     "normals": (0.286, 0.098)}, "normals"),
        ("retail_l", {"contour": (0.346, 0.835), "histogram": (0.334, 0.802),
                      "normals": (0.439, 0.748)}, "contour"),
        ("retail_s", {"contour": (0.224, 0.730), "histogram": (0.375, 0.766),
                      "normals": (0.497, 0.758)}, "histogram"),
        ("rohbau_07000", {"contour": (0.000, 0.000), "histogram": (0.885, 0.264),
                          "normals": (0.692, 0.291)}, "histogram"),
        ("rohbau_07001", {"contour": (0.011, 0.082), "histogram": (0.807, 0.253),
                          "normals": (0.624, 0.302)}, "histogram"),
        ("rohbau_07002", {"contour": (0.000, 0.000), "histogram": (0.959, 0.397),
                          "normals": (0.846, 0.415)}, "histogram"),
        ("rohbau_07003", {"contour": (0.000, 0.000), "histogram": (0.921, 0.288),
                          "normals": (0.847, 0.228)}, "histogram"),
        ("rohbau_07004", {"contour": (0.000, 0.000), "histogram": (0.866, 0.251),
                          "normals": (0.613, 0.197)}, "histogram"),
    ],
)
def test_mitatut_aineistot_valitsevat_samoin(choose, nimi, luvut, odotus):
    """Saannon vaihto ei saa siirtaa yhtaakaan mitattua valintaa."""
    assert choose(luvut) == odotus

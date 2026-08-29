"""Kehitysajan luokkavälimuisti: sama tulos, ei uutta inferenssiä."""
import numpy as np
import pytest

from scan2bim.core.segmentation.pointnet_filter import PointNetFilter


def _pts(n=5000):
    rng = np.random.RandomState(0)
    return rng.uniform(0.0, 3000.0, size=(n, 3))


def test_cache_is_off_without_the_env_var(monkeypatch):
    monkeypatch.delenv("SCAN2BIM_SEM_CACHE_DIR", raising=False)
    assert PointNetFilter._cache_path(_pts()) is None


def test_second_call_reads_the_cache_instead_of_inferring(monkeypatch, tmp_path):
    monkeypatch.setenv("SCAN2BIM_SEM_CACHE_DIR", str(tmp_path))
    f = PointNetFilter()
    pts = _pts()
    calls = []

    def fake(p):
        calls.append(1)
        n = 128
        return (np.zeros(n, dtype=np.int8), p.min(axis=0),
                np.arange(n, dtype=np.int64),
                np.zeros(len(p), dtype=np.int64))

    monkeypatch.setattr(f, "_classify_voxels_uncached", fake)
    a = f._classify_voxels(pts)
    b = f._classify_voxels(pts)
    assert len(calls) == 1, "toinen kutsu ajoi inferenssin uudestaan"
    for x, y in zip(a, b):
        assert np.array_equal(x, y)


def test_a_different_cloud_does_not_hit_the_same_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("SCAN2BIM_SEM_CACHE_DIR", str(tmp_path))
    p1, p2 = _pts(), _pts() + 10.0
    assert PointNetFilter._cache_path(p1) != PointNetFilter._cache_path(p2)

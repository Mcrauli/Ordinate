"""Lohkoluvun raja on mitoitettava koko keilausprojektille, ei yhdelle tiedostolle."""
from ordinate.core.geometry import loader


class _Header:
    def __init__(self, n):
        self.point_count = n
        self.point_fields = ("cartesianX", "cartesianY", "cartesianZ")


class _FakeE57:
    def __init__(self, n_points):
        self.scan_count = 1
        self._n = n_points

    def get_header(self, _i):
        return _Header(self._n)


def _patch(monkeypatch, n_points):
    import sys
    import types
    fake = types.ModuleType("pye57")
    fake.E57 = lambda _p: _FakeE57(n_points)
    monkeypatch.setitem(sys.modules, "pye57", fake)


def test_one_medium_file_is_read_whole(monkeypatch):
    """Yksi 27 M pisteen skanni mahtuu muistiin — lohkoluku muuttaisi tulosta
    (mitattu gargage.e57: 11 → 9 seinää), joten sitä ei saa ottaa turhaan."""
    _patch(monkeypatch, 27_000_000)
    assert loader._e57_is_chunkable("x.e57", 1) is False


def test_a_single_huge_file_is_chunked(monkeypatch):
    _patch(monkeypatch, 60_000_000)
    assert loader._e57_is_chunkable("x.e57", 1) is True


def test_many_medium_files_are_chunked(monkeypatch):
    """Koulun kellari: 36 asemaa á 27 M = miljardi pistettä yhteen pilveen.

    Jokainen alittaa 40 M rajan yksinään, mutta `load_floor_slice` kasaa ne
    samaan pilveen ja ajo kaatui `bad allocation`-virheeseen.
    """
    _patch(monkeypatch, 27_000_000)
    assert loader._e57_is_chunkable("x.e57", 36) is True


def test_a_small_file_stays_whole_even_in_a_big_project(monkeypatch):
    """Raja ei saa valua niin alas että pikkuskanni lohkoluetaan turhaan."""
    _patch(monkeypatch, 500_000)
    assert loader._e57_is_chunkable("x.e57", 36) is False
